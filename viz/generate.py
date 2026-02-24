#!/usr/bin/env python3
"""Generate interactive Pyvis HTML visualization of the knowledge graph."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pyvis.network import Network

from aivc.graph import COMPANY, FIRM, INVESTED_IN, PARTNER_AT, PERSONAL_INVESTMENT, PERSON, KnowledgeGraph

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
OUTPUT_DIR = Path(__file__).resolve().parent / "output"

# Bloomberg terminal color scheme
COLORS = {
    FIRM: "#FF8C00",       # Amber/Orange – VC firms
    COMPANY: "#00D67E",    # Terminal green – companies
    PERSON: "#00BFFF",     # Bright cyan – people
}

EDGE_COLORS = {
    INVESTED_IN: "#5A5A5A",
    PARTNER_AT: "#B8860B",
    PERSONAL_INVESTMENT: "#8B4513",
}

MONO_FONT = "'SF Mono', 'Fira Code', 'Cascadia Code', 'Consolas', 'Monaco', monospace"


def generate_html(
    graph_path: str | Path | None = None,
    output_path: str | Path | None = None,
    height: str = "900px",
    width: str = "100%",
) -> Path:
    """Generate an interactive Pyvis HTML file from the knowledge graph."""
    graph_path = Path(graph_path) if graph_path else DATA_DIR / "graph.json"
    output_path = Path(output_path) if output_path else OUTPUT_DIR / "graph.html"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    kg = KnowledgeGraph.load(graph_path)

    net = Network(
        height=height,
        width=width,
        directed=True,
        bgcolor="#0A0A0A",
        font_color=True,
        notebook=False,
        cdn_resources="remote",
    )

    # Physics settings for better layout
    net.set_options("""
    {
        "nodes": {
            "font": {
                "size": 14,
                "color": "#C8C8C8"
            }
        },
        "edges": {
            "font": {
                "size": 12,
                "color": "#888888",
                "strokeWidth": 0,
                "strokeColor": "transparent"
            }
        },
        "physics": {
            "forceAtlas2Based": {
                "gravitationalConstant": -150,
                "centralGravity": 0.008,
                "springLength": 250,
                "springConstant": 0.015,
                "damping": 0.4
            },
            "solver": "forceAtlas2Based",
            "stabilization": {
                "iterations": 300
            },
            "maxVelocity": 50,
            "minVelocity": 0.75
        },
        "interaction": {
            "hover": true,
            "tooltipDelay": 200
        }
    }
    """)

    # Identify edges and companies with investments dated within the last 7 days
    now = datetime.now()
    recent_cutoff = now - timedelta(days=7)
    recent_edges: set[tuple[str, str]] = set()   # (src, dst) pairs
    recent_company_ids: set[str] = set()
    for src, dst, data in kg.g.edges(data=True):
        if data.get("edge_type") != INVESTED_IN:
            continue
        date_str = data.get("date", "")
        if not date_str:
            continue
        try:
            is_recent = False
            if len(date_str) >= 10:
                edge_date = datetime.strptime(date_str[:10], "%Y-%m-%d")
                is_recent = edge_date >= recent_cutoff
            elif len(date_str) >= 7:
                y, m = int(date_str[:4]), int(date_str[5:7])
                is_recent = (y == now.year and m == now.month)
            if is_recent:
                recent_edges.add((src, dst))
                recent_company_ids.add(dst)
        except ValueError:
            pass

    RECENT_COLOR = "#FF2020"  # bright red for recent investments

    # Add nodes and build metadata labels for focus mode
    node_detail_labels = {}  # nid -> multi-line detail label (for focus mode)
    node_images = {}  # nid -> {image, brokenImage} for focus mode
    node_urls = {}  # nid -> URL (for clickable links)
    for nid, attrs in kg.g.nodes(data=True):
        node_type = attrs.get("node_type", "unknown")
        name = attrs.get("name", nid)
        color = COLORS.get(node_type, "#CCCCCC")

        # Size based on connectivity
        degree = kg.g.degree(nid)
        size = max(10, min(50, 8 + degree * 3))

        # Highlight companies with investments in the last 7 days
        is_recent = nid in recent_company_ids and node_type == COMPANY
        if is_recent:
            color = RECENT_COLOR
            size = max(size, 35)  # ensure visibility

        # Resolve URL for this node
        url = ""
        if node_type == FIRM and attrs.get("website"):
            url = attrs["website"]
        elif node_type == COMPANY and attrs.get("website"):
            url = attrs["website"]
        elif node_type == PERSON and attrs.get("linkedin"):
            url = attrs["linkedin"]
        if url and not url.startswith("http"):
            url = "https://" + url
        if url:
            node_urls[nid] = url

        # Derive node image (logo or avatar)
        website = attrs.get("website", "")
        domain = website.strip().removeprefix("https://").removeprefix("http://").split("/")[0] if website else ""
        bg_hex = color.lstrip("#")
        encoded_name = quote(name)
        fallback_url = f"https://ui-avatars.com/api/?name={encoded_name}&background={bg_hex}&color=fff&size=128&bold=true"

        if node_type == PERSON:
            image_url = fallback_url
        elif domain:
            image_url = f"https://www.google.com/s2/favicons?domain={domain}&sz=128"
        else:
            image_url = fallback_url

        node_images[nid] = {"image": image_url, "brokenImage": fallback_url}

        # Build tooltip (HTML for hover popup) — includes logo/avatar image
        logo_img = f'<img src="{image_url}" onerror="this.src=\'{fallback_url}\'" style="width:36px;height:36px;border-radius:50%;vertical-align:middle;margin-right:8px;border:2px solid {color};background:#111;">'
        name_html = f'<a href="{url}" target="_blank" style="color:#00D67E;text-decoration:underline;">{name}</a>' if url else name
        title_parts = [f"{logo_img}<b>{name_html}</b> <span style='color:#888;'>({node_type})</span>"]
        # Build detail label (plain text for focus mode, shown inside node)
        detail_parts = [name]
        if node_type == FIRM:
            if attrs.get("hq_city"):
                title_parts.append(f"HQ: {attrs['hq_city']}")
                detail_parts.append(attrs["hq_city"])
            if attrs.get("ai_focus"):
                title_parts.append(f"Focus: {attrs['ai_focus']}")
                focus = attrs["ai_focus"]
                if len(focus) > 40:
                    focus = focus[:37] + "..."
                detail_parts.append(focus)
            if attrs.get("aum"):
                title_parts.append(f"AUM: {attrs['aum']}")
                detail_parts.append(attrs["aum"])
            if attrs.get("stage_focus"):
                detail_parts.append(attrs["stage_focus"])
        elif node_type == PERSON:
            if attrs.get("title"):
                title_parts.append(f"Title: {attrs['title']}")
                detail_parts.append(attrs["title"])
        elif node_type == COMPANY:
            if attrs.get("sector"):
                title_parts.append(f"Sector: {attrs['sector']}")
                detail_parts.append(attrs["sector"])
            if attrs.get("founded_year"):
                title_parts.append(f"Founded: {attrs['founded_year']}")
                detail_parts.append(f"Est. {attrs['founded_year']}")
            if attrs.get("website"):
                title_parts.append(f"Web: {attrs['website']}")

        title = "<br>".join(title_parts)
        node_detail_labels[nid] = "\n".join(detail_parts)

        net.add_node(
            nid, label=name, color=color, size=size, title=title,
            font={"size": 14, "color": "#C8C8C8"},
        )

    # Add edges and collect metadata for timeline + focus mode
    edge_dates = {}       # "src||dst" -> year (for timeline)
    edge_detail_labels = {}  # "src||dst" -> label string (for focus mode)
    for src, dst, data in kg.g.edges(data=True):
        edge_type = data.get("edge_type", "")
        color = EDGE_COLORS.get(edge_type, "#CCCCCC")

        title_parts = [edge_type]
        label_parts = []
        if data.get("date"):
            title_parts.append(f"Date: {data['date']}")
            label_parts.append(data["date"])
        if data.get("amount"):
            title_parts.append(f"Amount: {data['amount']}")
            label_parts.append(data["amount"])
        if data.get("round"):
            title_parts.append(f"Round: {data['round']}")
            label_parts.append(data["round"])
        if data.get("title") and edge_type == "partner_at":
            label_parts.append(data["title"])
        title = "<br>".join(title_parts)

        edge_key = f"{src}||{dst}"
        edge_detail_labels[edge_key] = " | ".join(label_parts) if label_parts else edge_type.replace("_", " ")

        # Highlight only the specific recent investment edges
        edge_width = 1
        if (src, dst) in recent_edges:
            color = RECENT_COLOR
            edge_width = 3

        net.add_edge(src, dst, color=color, title=title, arrows="to", width=edge_width)

        # Track date for timeline
        date_str = data.get("date", "")
        if date_str:
            try:
                year = int(date_str[:4])
                edge_dates[edge_key] = year
            except ValueError:
                pass

    # Compute year range
    if edge_dates:
        min_year = min(edge_dates.values())
        max_year = max(edge_dates.values())
    else:
        min_year, max_year = 2000, 2025

    # Default lower-bound at 2025 (clamped to actual range)
    default_min_year = max(min_year, min(2025, max_year))

    net.save_graph(str(output_path))

    # Build the edge-dates JS data and inject timeline + legend into HTML
    html = output_path.read_text()

    # Remove the card wrapper that pyvis adds (causes a visible border from Bootstrap)
    html = html.replace('<div class="card" style="width: 100%">', '<div style="width:100%">')
    html = html.replace('class="card-body"', '')

    # Add page title
    title_html = """<title>AI VC - What's Going On</title>"""
    html = html.replace("<head>", "<head>\n" + title_html)

    header_html = """
<div id="page-header" style="
    position: fixed;
    top: 0; left: 0; right: 0;
    background: rgba(10,10,10,0.97);
    padding: 10px 24px;
    z-index: 9999;
    border-bottom: 1px solid #222;
    font-family: 'SF Mono', 'Fira Code', 'Cascadia Code', 'Consolas', 'Monaco', monospace;
">
    <div style="max-width:1200px; margin:0 auto; display:flex; align-items:baseline; gap:12px;">
        <span style="font-size:22px; font-weight:700; color:#FF8C00; letter-spacing:2px;">AI VC</span>
        <span style="font-size:13px; color:#555; letter-spacing:1px; text-transform:uppercase;">What's Going On</span>
        <span style="flex:1;"></span>
        <span id="node-count" style="font-size:11px; color:#00D67E;"></span>
    </div>
</div>
<style>
    body { background: #0A0A0A !important; margin: 0; }
    #mynetwork { margin-top: 48px !important; background: #0A0A0A !important; }
    .card { border: none !important; box-shadow: none !important; margin: 0 !important; padding: 0 !important; background: transparent !important; }
    .card-body { background: transparent !important; }
    ::selection { background: #FF8C00; color: #000; }
    ::-webkit-scrollbar { width: 6px; }
    ::-webkit-scrollbar-track { background: #111; }
    ::-webkit-scrollbar-thumb { background: #333; border-radius: 3px; }
</style>
"""
    html = html.replace("<body>", "<body>\n" + header_html)

    inject = _build_timeline_and_legend_html(
        edge_dates, min_year, max_year, default_min_year, node_detail_labels, edge_detail_labels, node_urls, node_images
    )
    html = html.replace("</body>", inject + "</body>")
    output_path.write_text(html)

    return output_path


def _build_timeline_and_legend_html(
    edge_dates: dict[str, int],
    min_year: int,
    max_year: int,
    default_min_year: int,
    node_detail_labels: dict[str, str],
    edge_detail_labels: dict[str, str],
    node_urls: dict[str, str],
    node_images: dict[str, dict[str, str]],
) -> str:
    """Build the HTML/CSS/JS for the timeline slider, legend, and interactions."""
    edge_dates_json = json.dumps(edge_dates)
    node_labels_json = json.dumps(node_detail_labels, ensure_ascii=False)
    edge_labels_json = json.dumps(edge_detail_labels, ensure_ascii=False)
    node_urls_json = json.dumps(node_urls, ensure_ascii=False)
    node_images_json = json.dumps(node_images, ensure_ascii=False)

    return f"""
<!-- Legend -->
<div id="graph-legend" style="
    position: fixed;
    bottom: 80px;
    right: 20px;
    background: rgba(15,15,15,0.95);
    border: 1px solid #333;
    border-radius: 4px;
    padding: 12px 16px;
    font-family: 'SF Mono', 'Fira Code', 'Cascadia Code', 'Consolas', 'Monaco', monospace;
    font-size: 11px;
    z-index: 9999;
    line-height: 1.8;
    color: #AAA;
">
    <div style="font-weight: 600; margin-bottom: 4px; font-size: 11px; color: #666; text-transform: uppercase; letter-spacing: 1px;">Legend</div>
    <div><span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:#FF8C00;margin-right:8px;vertical-align:middle;"></span><span style="color:#FF8C00;">VC Firm</span></div>
    <div><span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:#00D67E;margin-right:8px;vertical-align:middle;"></span><span style="color:#00D67E;">Company</span></div>
    <div><span style="display:inline-block;width:14px;height:14px;border-radius:50%;background:#FF2020;margin-right:6px;vertical-align:middle;box-shadow:0 0 8px rgba(255,32,32,0.6);"></span><span style="color:#FF2020;">Recent (7d)</span></div>
    <div><span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:#00BFFF;margin-right:8px;vertical-align:middle;"></span><span style="color:#00BFFF;">Person</span></div>
    <hr style="margin:6px 0;border:none;border-top:1px solid #2A2A2A;">
    <div><span style="display:inline-block;width:16px;height:1px;background:#5A5A5A;margin-right:8px;vertical-align:middle;"></span>Invested in</div>
    <div><span style="display:inline-block;width:16px;height:1px;background:#B8860B;margin-right:8px;vertical-align:middle;"></span>Partner at</div>
    <div><span style="display:inline-block;width:16px;height:1px;background:#8B4513;margin-right:8px;vertical-align:middle;"></span>Personal inv.</div>
</div>

<!-- Timeline Bar -->
<style>
    #timeline-bar {{
        position: fixed;
        bottom: 0; left: 0; right: 0;
        background: rgba(10,10,10,0.97);
        border-top: 1px solid #222;
        padding: 10px 24px 14px;
        font-family: 'SF Mono', 'Fira Code', 'Cascadia Code', 'Consolas', 'Monaco', monospace;
        font-size: 11px;
        z-index: 9999;
        color: #AAA;
    }}
    .range-slider {{
        position: relative;
        height: 28px;
        flex: 1;
    }}
    .range-slider .track {{
        position: absolute;
        top: 12px; left: 0; right: 0;
        height: 2px;
        background: #333;
        border-radius: 1px;
    }}
    .range-slider .highlight {{
        position: absolute;
        top: 12px;
        height: 2px;
        background: #FF8C00;
        border-radius: 1px;
    }}
    .range-slider input[type=range] {{
        position: absolute;
        top: 0; left: 0;
        width: 100%;
        height: 28px;
        margin: 0;
        -webkit-appearance: none;
        appearance: none;
        background: transparent;
        pointer-events: none;
        z-index: 2;
    }}
    .range-slider input[type=range]::-webkit-slider-thumb {{
        -webkit-appearance: none;
        appearance: none;
        width: 14px; height: 14px;
        border-radius: 50%;
        background: #FF8C00;
        border: 2px solid #0A0A0A;
        box-shadow: 0 0 6px rgba(255,140,0,0.4);
        cursor: pointer;
        pointer-events: auto;
    }}
    .range-slider input[type=range]::-moz-range-thumb {{
        width: 14px; height: 14px;
        border-radius: 50%;
        background: #FF8C00;
        border: 2px solid #0A0A0A;
        box-shadow: 0 0 6px rgba(255,140,0,0.4);
        cursor: pointer;
        pointer-events: auto;
    }}
    .tl-ticks {{
        display: flex;
        justify-content: space-between;
        padding: 0;
        margin-top: 2px;
    }}
    .tl-ticks span {{
        font-size: 9px;
        color: #444;
        min-width: 0;
        text-align: center;
    }}
</style>
<div id="timeline-bar">
    <div style="display:flex; align-items:center; gap:14px; max-width:1200px; margin:0 auto;">
        <span style="font-weight:600; white-space:nowrap; color:#666; text-transform:uppercase; letter-spacing:1px; font-size:10px;">Timeline</span>
        <span id="year-min-label" style="min-width:36px; text-align:right; font-variant-numeric:tabular-nums; font-weight:500; color:#FF8C00;">{default_min_year}</span>
        <div class="range-slider">
            <div class="track"></div>
            <div class="highlight" id="range-highlight"></div>
            <input type="range" id="year-min" min="{min_year}" max="{max_year}" value="{default_min_year}">
            <input type="range" id="year-max" min="{min_year}" max="{max_year}" value="{max_year}">
        </div>
        <span id="year-max-label" style="min-width:36px; font-variant-numeric:tabular-nums; font-weight:500; color:#FF8C00;">{max_year}</span>
        <span id="timeline-info" style="color:#00D67E; white-space:nowrap; min-width:140px; font-size:11px;"></span>
        <button id="timeline-reset" style="
            padding: 3px 10px; border: 1px solid #333; border-radius: 2px;
            background: #1A1A1A; color: #AAA; cursor: pointer; font-size: 10px;
            white-space: nowrap; font-family: inherit; text-transform: uppercase; letter-spacing: 0.5px;
        " onmouseover="this.style.borderColor='#FF8C00';this.style.color='#FF8C00'" onmouseout="this.style.borderColor='#333';this.style.color='#AAA'">Reset</button>
    </div>
    <div class="tl-ticks" style="max-width:1200px; margin:0 auto; padding-left:104px; padding-right:232px;">
        {''.join(f'<span>{y}</span>' for y in range(min_year, max_year + 1, max(1, (max_year - min_year) // 10)))}
    </div>
</div>

<script>
(function() {{
    var edgeDates = {edge_dates_json};
    var YEAR_MIN = {min_year}, YEAR_MAX = {max_year};

    var sliderMin = document.getElementById('year-min');
    var sliderMax = document.getElementById('year-max');
    var labelMin = document.getElementById('year-min-label');
    var labelMax = document.getElementById('year-max-label');
    var highlight = document.getElementById('range-highlight');
    var info = document.getElementById('timeline-info');
    var resetBtn = document.getElementById('timeline-reset');

    function updateHighlight() {{
        var lo = parseInt(sliderMin.value), hi = parseInt(sliderMax.value);
        var pctLo = (lo - YEAR_MIN) / (YEAR_MAX - YEAR_MIN) * 100;
        var pctHi = (hi - YEAR_MIN) / (YEAR_MAX - YEAR_MIN) * 100;
        highlight.style.left = pctLo + '%';
        highlight.style.width = (pctHi - pctLo) + '%';
    }}

    // Prevent thumbs from crossing each other
    sliderMin.addEventListener('input', function() {{
        if (parseInt(sliderMin.value) > parseInt(sliderMax.value)) {{
            sliderMin.value = sliderMax.value;
        }}
        updateHighlight();
    }});
    sliderMax.addEventListener('input', function() {{
        if (parseInt(sliderMax.value) < parseInt(sliderMin.value)) {{
            sliderMax.value = sliderMin.value;
        }}
        updateHighlight();
    }});

    updateHighlight();

    // Wait for vis.js network to be ready
    var checkReady = setInterval(function() {{
        if (typeof network === 'undefined' || typeof edges === 'undefined' || typeof nodes === 'undefined') return;
        clearInterval(checkReady);
        initTimeline();
    }}, 200);

    function initTimeline() {{
        var allEdges = edges.get();
        var allNodes = nodes.get();

        var edgeYearMap = {{}};
        allEdges.forEach(function(e) {{
            var key = e.from + '||' + e.to;
            if (edgeDates[key] !== undefined) edgeYearMap[e.id] = edgeDates[key];
        }});

        var originalEdges = {{}};
        allEdges.forEach(function(e) {{ originalEdges[e.id] = {{ color: e.color }}; }});
        var originalNodes = {{}};
        allNodes.forEach(function(n) {{ originalNodes[n.id] = {{ color: n.color }}; }});

        function applyFilter() {{
            var yMin = parseInt(sliderMin.value), yMax = parseInt(sliderMax.value);
            labelMin.textContent = yMin;
            labelMax.textContent = yMax;

            var visibleNodes = new Set();
            var visibleEdges = 0, hiddenEdges = 0;
            var edgeUpdates = [];

            allEdges.forEach(function(e) {{
                var year = edgeYearMap[e.id];
                var visible = (year === undefined) ? true : (year >= yMin && year <= yMax);
                if (visible) {{
                    visibleEdges++;
                    visibleNodes.add(e.from);
                    visibleNodes.add(e.to);
                    edgeUpdates.push({{ id: e.id, hidden: false, color: originalEdges[e.id].color }});
                }} else {{
                    hiddenEdges++;
                    edgeUpdates.push({{ id: e.id, hidden: true }});
                }}
            }});
            edges.update(edgeUpdates);

            var nodeUpdates = [];
            allNodes.forEach(function(n) {{
                if (visibleNodes.has(n.id)) {{
                    nodeUpdates.push({{ id: n.id, hidden: false, opacity: 1, color: originalNodes[n.id].color }});
                }} else {{
                    nodeUpdates.push({{ id: n.id, hidden: false, opacity: 0.1, color: '#1A1A1A' }});
                }}
            }});
            nodes.update(nodeUpdates);

            info.textContent = visibleEdges + ' shown, ' + hiddenEdges + ' hidden';
        }}

        sliderMin.addEventListener('input', applyFilter);
        sliderMax.addEventListener('input', applyFilter);

        resetBtn.addEventListener('click', function() {{
            sliderMin.value = YEAR_MIN;
            sliderMax.value = YEAR_MAX;
            updateHighlight();
            var edgeUpdates = allEdges.map(function(e) {{
                return {{ id: e.id, hidden: false, color: originalEdges[e.id].color }};
            }});
            edges.update(edgeUpdates);
            var nodeUpdates = allNodes.map(function(n) {{
                return {{ id: n.id, hidden: false, opacity: 1, color: originalNodes[n.id].color }};
            }});
            nodes.update(nodeUpdates);
            labelMin.textContent = YEAR_MIN;
            labelMax.textContent = YEAR_MAX;
            info.textContent = '';
        }});

        applyFilter();
    }}
}})();
</script>

<!-- Custom HTML tooltip + double-click to open URL -->
<style>
    .vis-tooltip {{ display: none !important; }}
    #custom-tooltip {{
        position: absolute;
        display: none;
        background: rgba(20,20,20,0.97);
        border: 1px solid #333;
        border-left: 3px solid #FF8C00;
        border-radius: 2px;
        padding: 8px 12px;
        font-family: 'SF Mono', 'Fira Code', 'Cascadia Code', 'Consolas', 'Monaco', monospace;
        font-size: 12px;
        line-height: 1.6;
        max-width: 420px;
        color: #CCC;
        pointer-events: auto;
        z-index: 10000;
    }}
    #custom-tooltip b {{
        color: #EEE;
    }}
    #custom-tooltip a {{
        color: #00D67E;
        text-decoration: none;
    }}
    #custom-tooltip a:hover {{
        color: #00FFB0;
        text-decoration: underline;
    }}
</style>
<div id="custom-tooltip"></div>
<script>
(function() {{
    var tooltip = document.getElementById('custom-tooltip');
    var nodeUrls = {node_urls_json};
    var hideTimer = null;

    function checkReady() {{
        if (typeof network === 'undefined' || typeof nodes === 'undefined' || typeof edges === 'undefined') {{
            setTimeout(checkReady, 200);
            return;
        }}
        initTooltip();
    }}
    checkReady();

    function initTooltip() {{
        var nodeMap = {{}};
        nodes.get().forEach(function(n) {{ nodeMap[n.id] = n; }});
        var edgeMap = {{}};
        edges.get().forEach(function(e) {{ edgeMap[e.id] = e; }});

        var container = document.getElementById('mynetwork') || document.querySelector('.vis-network');

        function showTip(htmlContent, event) {{
            if (!htmlContent) return;
            clearTimeout(hideTimer);
            tooltip.innerHTML = htmlContent;
            tooltip.style.display = 'block';
            var x = event.clientX + 14;
            var y = event.clientY + 14;
            if (x + 350 > window.innerWidth) x = event.clientX - 350;
            if (y + 100 > window.innerHeight) y = event.clientY - 100;
            tooltip.style.left = x + 'px';
            tooltip.style.top = y + 'px';
        }}

        function hideTip() {{
            hideTimer = setTimeout(function() {{
                tooltip.style.display = 'none';
            }}, 200);
        }}

        // Keep tooltip visible while mouse is over it (so links are clickable)
        tooltip.addEventListener('mouseenter', function() {{ clearTimeout(hideTimer); }});
        tooltip.addEventListener('mouseleave', function() {{ hideTip(); }});

        var lastMouseEvent = null;
        if (container) {{
            container.addEventListener('mousemove', function(e) {{ lastMouseEvent = e; }});
        }}

        network.on('hoverNode', function(params) {{
            var node = nodeMap[params.node];
            if (node && node.title && lastMouseEvent) {{
                showTip(node.title, lastMouseEvent);
            }}
        }});

        network.on('blurNode', function() {{ hideTip(); }});

        network.on('hoverEdge', function(params) {{
            var edge = edgeMap[params.edge];
            if (edge && edge.title && lastMouseEvent) {{
                showTip(edge.title, lastMouseEvent);
            }}
        }});

        network.on('blurEdge', function() {{ hideTip(); }});

        network.on('dragStart', function() {{ clearTimeout(hideTimer); tooltip.style.display = 'none'; }});
        network.on('zoom', function() {{ clearTimeout(hideTimer); tooltip.style.display = 'none'; }});

        // Double-click a node to open its URL
        network.on('doubleClick', function(params) {{
            if (params.nodes.length === 1) {{
                var url = nodeUrls[params.nodes[0]];
                if (url) window.open(url, '_blank');
            }}
        }});
    }}
}})();
</script>

<!-- Click-to-focus: zoom into subgraph, show metadata in nodes and on edges -->
<script>
(function() {{
    // Detail labels and images for focus mode
    var nodeDetailLabels = {node_labels_json};
    var edgeDetailLabels = {edge_labels_json};
    var nodeImages = {node_images_json};

    function checkReady() {{
        if (typeof network === 'undefined' || typeof nodes === 'undefined' || typeof edges === 'undefined') {{
            setTimeout(checkReady, 200);
            return;
        }}
        initClickFocus();
    }}
    checkReady();

    function initClickFocus() {{
        var allNodes = nodes.get();
        var allEdges = edges.get();

        // Store original properties
        var origNode = {{}};
        allNodes.forEach(function(n) {{
            origNode[n.id] = {{
                color: n.color,
                size: n.size,
                label: n.label,
                font: n.font || {{}},
                borderWidth: n.borderWidth || 1,
                shape: n.shape || 'dot'
            }};
        }});
        var origEdge = {{}};
        allEdges.forEach(function(e) {{
            origEdge[e.id] = {{
                color: e.color,
                width: e.width || 1,
                label: e.label || undefined,
                font: e.font || {{}}
            }};
        }});

        var focusedNode = null;

        // Build adjacency
        var adjEdges = {{}};
        var adjNodes = {{}};
        allNodes.forEach(function(n) {{ adjEdges[n.id] = []; adjNodes[n.id] = new Set(); }});
        allEdges.forEach(function(e) {{
            if (adjEdges[e.from]) {{ adjEdges[e.from].push(e.id); adjNodes[e.from].add(e.to); }}
            if (adjEdges[e.to]) {{ adjEdges[e.to].push(e.id); adjNodes[e.to].add(e.from); }}
        }});

        // Map edge id -> "from||to" key for label lookup
        var edgeKeyMap = {{}};
        allEdges.forEach(function(e) {{ edgeKeyMap[e.id] = e.from + '||' + e.to; }});

        function focusOn(nodeId) {{
            focusedNode = nodeId;
            var neighborSet = adjNodes[nodeId] || new Set();
            var connectedEdgeIds = new Set(adjEdges[nodeId] || []);
            var subgraphNodeIds = [nodeId].concat(Array.from(neighborSet));

            // Update nodes: show metadata labels
            var nodeUpdates = [];
            allNodes.forEach(function(n) {{
                var img = nodeImages[n.id];
                if (n.id === nodeId) {{
                    var upd = {{
                        id: n.id,
                        label: nodeDetailLabels[n.id] || origNode[n.id].label,
                        size: Math.max(40, (origNode[n.id].size || 15) * 2.5),
                        color: {{ background: '#1A1A1A', border: origNode[n.id].color }},
                        borderWidth: 3,
                        font: {{ size: 22, color: '#EEE', face: "'SF Mono','Consolas',monospace", multi: false, align: 'center', strokeWidth: 0 }},
                        opacity: 1
                    }};
                    if (img) {{
                        upd.shape = 'circularImage';
                        upd.image = img.image;
                        upd.brokenImage = img.brokenImage;
                    }} else {{
                        upd.shape = 'box';
                    }}
                    nodeUpdates.push(upd);
                }} else if (neighborSet.has(n.id)) {{
                    var upd2 = {{
                        id: n.id,
                        label: nodeDetailLabels[n.id] || origNode[n.id].label,
                        size: Math.max(30, (origNode[n.id].size || 15) * 1.5),
                        color: {{ background: '#111', border: origNode[n.id].color }},
                        borderWidth: 2,
                        font: {{ size: 18, color: '#CCC', face: "'SF Mono','Consolas',monospace", multi: false, align: 'center', strokeWidth: 0 }},
                        opacity: 1
                    }};
                    if (img) {{
                        upd2.shape = 'circularImage';
                        upd2.image = img.image;
                        upd2.brokenImage = img.brokenImage;
                    }} else {{
                        upd2.shape = 'box';
                    }}
                    nodeUpdates.push(upd2);
                }} else {{
                    nodeUpdates.push({{
                        id: n.id,
                        label: '',
                        size: origNode[n.id].size,
                        color: '#111',
                        borderWidth: 0,
                        shape: origNode[n.id].shape,
                        font: {{ color: 'rgba(0,0,0,0)' }},
                        opacity: 0.05
                    }});
                }}
            }});
            nodes.update(nodeUpdates);

            // Update edges: show labels on connected, dim the rest
            var edgeUpdates = [];
            allEdges.forEach(function(e) {{
                if (connectedEdgeIds.has(e.id)) {{
                    var key = edgeKeyMap[e.id];
                    var lbl = edgeDetailLabels[key] || '';
                    edgeUpdates.push({{
                        id: e.id,
                        color: {{ color: origEdge[e.id].color, highlight: origEdge[e.id].color }},
                        width: 3,
                        label: lbl,
                        font: {{ size: 16, color: '#888', strokeWidth: 0, align: 'top' }},
                        hidden: false
                    }});
                }} else {{
                    edgeUpdates.push({{
                        id: e.id,
                        color: 'rgba(30,30,30,0.2)',
                        width: 0.3,
                        label: undefined,
                        font: {{ color: 'rgba(0,0,0,0)' }},
                        hidden: false
                    }});
                }}
            }});
            edges.update(edgeUpdates);

            // Zoom to fit the subgraph
            network.fit({{
                nodes: subgraphNodeIds,
                animation: {{ duration: 500, easingFunction: 'easeInOutQuad' }}
            }});
        }}

        function resetFocus() {{
            focusedNode = null;
            var nodeUpdates = allNodes.map(function(n) {{
                return {{
                    id: n.id,
                    label: origNode[n.id].label,
                    size: origNode[n.id].size,
                    color: origNode[n.id].color,
                    borderWidth: origNode[n.id].borderWidth,
                    font: origNode[n.id].font,
                    shape: origNode[n.id].shape,
                    image: undefined,
                    brokenImage: undefined,
                    opacity: 1
                }};
            }});
            nodes.update(nodeUpdates);

            var edgeUpdates = allEdges.map(function(e) {{
                return {{
                    id: e.id,
                    color: origEdge[e.id].color,
                    width: origEdge[e.id].width,
                    label: origEdge[e.id].label,
                    font: origEdge[e.id].font,
                    hidden: false
                }};
            }});
            edges.update(edgeUpdates);

            // Zoom back to full view
            network.fit({{
                animation: {{ duration: 400, easingFunction: 'easeInOutQuad' }}
            }});
        }}

        network.on('selectNode', function(params) {{
            if (params.nodes.length === 1) {{
                focusOn(params.nodes[0]);
            }}
        }});

        network.on('deselectNode', function() {{
            resetFocus();
        }});

        network.on('click', function(params) {{
            if (params.nodes.length === 0 && params.edges.length === 0 && focusedNode) {{
                resetFocus();
            }}
        }});
    }}
}})();
</script>

<!-- Node/edge counter in header -->
<script>
(function() {{
    function updateCount() {{
        if (typeof nodes === 'undefined' || typeof edges === 'undefined') {{
            setTimeout(updateCount, 300);
            return;
        }}
        var el = document.getElementById('node-count');
        if (el) el.textContent = nodes.length + ' nodes | ' + edges.length + ' edges';
    }}
    updateCount();
}})();
</script>

<!-- Loading bar override for dark theme -->
<style>
    .vis-loading-bar {{ background: #0A0A0A !important; }}
    .vis-loading-bar .bar {{ background: #FF8C00 !important; }}
    .vis-loading-bar .text {{ color: #666 !important; font-family: 'SF Mono','Consolas',monospace !important; }}
</style>
"""


def main():
    output = generate_html()
    print(f"Generated visualization at: {output}")


if __name__ == "__main__":
    main()
