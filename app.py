import streamlit as st
from pathlib import Path
import json
import re

st.set_page_config(page_title="AcuityAI Capability Map", layout="wide")


def get_block_text(block):
    block_type = block["type"]
    rich_texts = block.get(block_type, {}).get("rich_text", [])
    return "".join(rt["plain_text"] for rt in rich_texts)


def fetch_all_blocks(notion, block_id):
    all_blocks = []
    cursor = None
    while True:
        kwargs = {"block_id": block_id}
        if cursor:
            kwargs["start_cursor"] = cursor
        response = notion.blocks.children.list(**kwargs)
        all_blocks.extend(response["results"])
        if not response["has_more"]:
            break
        cursor = response["next_cursor"]
    for block in all_blocks:
        if block.get("has_children"):
            block["_children"] = fetch_all_blocks(notion, block["id"])
    return all_blocks


def blocks_to_text(blocks, depth=0):
    lines = []
    for block in blocks:
        block_type = block["type"]
        text = get_block_text(block)
        if block_type == "heading_1":
            lines.append(f"\n# {text}")
        elif block_type == "heading_2":
            lines.append(f"\n## {text}")
        elif block_type == "heading_3":
            lines.append(f"\n### {text}")
        elif block_type == "paragraph":
            lines.append(text)
        elif block_type in ("bulleted_list_item", "numbered_list_item"):
            indent = "  " * depth
            lines.append(f"{indent}* {text}")
        elif block_type == "toggle":
            lines.append(f"\n{text}")
        elif block_type == "divider":
            lines.append("---")
        elif block_type == "table_row":
            cells = block["table_row"]["cells"]
            row_text = " | ".join(
                "".join(rt["plain_text"] for rt in cell) for cell in cells
            )
            lines.append(row_text)
        if "_children" in block:
            lines.append(blocks_to_text(block["_children"], depth + 1))
    return "\n".join(lines)


@st.cache_data(ttl=86400)
def fetch_notion_content(page_id, _token):
    from notion_client import Client

    notion = Client(auth=_token)
    blocks = fetch_all_blocks(notion, page_id)
    return blocks_to_text(blocks)


@st.cache_data(ttl=86400)
def parse_capabilities(content, _api_key):
    import anthropic

    client = anthropic.Anthropic(api_key=_api_key)
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=8192,
        messages=[
            {
                "role": "user",
                "content": f"""Parse the following product capability document into a JSON array of capability categories for a medical device sales AI assistant.

Each item needs exactly these fields:
- "name": category name (e.g., "HCP Research & Profiling")
- "today": number 0.0-1.0 representing current coverage strength
- "nearterm": number 0.0-1.0 representing expected coverage in 3-6 months
- "longterm": number 0.0-1.0 representing expected coverage in 6-12+ months
- "tier": "strong" if today >= 0.75, "investing" if today >= 0.45, "gap" if today < 0.45
- "todayDesc": 1-2 sentence description of current capabilities
- "todayExample": example question a sales rep could ask today (in quotes)
- "roadmapDesc": 1-2 sentence description of what's planned
- "gapDesc": 1-2 sentence description of what's missing
- "gapExample": example question showing the gap (in quotes, ending with ' — not yet supported.')

Organize into 10-15 categories covering key sales rep workflows like: HCP Research, Account Research, Call & Meeting Prep, Territory Prioritization, Referral Networks, Sales Analytics, Next Best Action, Route Planning, Email & Outreach, Pipeline Management, CRM Updates, Document Search, Market Access, Similar Provider Discovery.

Score based on the depth and breadth of capabilities described. Be honest about gaps.

Return ONLY a valid JSON array. No markdown code fences, no explanation.

Document:
{content}""",
            }
        ],
    )
    text = response.content[0].text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return json.loads(text)


# --- Main ---
html_template = (Path(__file__).parent / "capability_map.html").read_text()

try:
    notion_token = st.secrets["NOTION_TOKEN"]
    notion_page_id = st.secrets["NOTION_PAGE_ID"]
    anthropic_key = st.secrets["ANTHROPIC_API_KEY"]

    content = fetch_notion_content(notion_page_id, notion_token)
    categories = parse_capabilities(content, anthropic_key)

    categories_json = json.dumps(categories, ensure_ascii=False)
    html_content = re.sub(
        r"/\*CATEGORIES_START\*/.*?/\*CATEGORIES_END\*/",
        f"/*CATEGORIES_START*/{categories_json}/*CATEGORIES_END*/",
        html_template,
        flags=re.DOTALL,
    )
except Exception:
    # Fall back to hardcoded data already in the HTML
    html_content = html_template

st.components.v1.html(html_content, height=2800, scrolling=True)
