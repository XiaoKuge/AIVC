#!/usr/bin/env python3
"""Generate interactive Pyvis HTML visualization of the knowledge graph."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pyvis.network import Network

from aivc.graph import COMPANY, FIRM, INVESTED_IN, PARTNER_AT, PERSONAL_INVESTMENT, PERSON, KnowledgeGraph

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
OUTPUT_DIR = Path(__file__).resolve().parent / "output"

# Color scheme
COLORS = {
    FIRM: "#4A90D9",       # Blue
    COMPANY: "#50C878",    # Green
    PERSON: "#FF8C42",     # Orange
}

EDGE_COLORS = {
    INVESTED_IN: "#888888",
    PARTNER_AT: "#CC8800",
    PERSONAL_INVESTMENT: "#DD6644",
}


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
        bgcolor="#FFFFFF",
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
                "color": "#000000"
            }
        },
        "edges": {
            "font": {
                "size": 12,
                "color": "#000000",
                "strokeWidth": 2,
                "strokeColor": "#ffffff"
            }
        },
        "physics": {
            "forceAtlas2Based": {
                "gravitationalConstant": -100,
                "centralGravity": 0.01,
                "springLength": 200,
                "springConstant": 0.02
            },
            "solver": "forceAtlas2Based",
            "stabilization": {
                "iterations": 150
            }
        },
        "interaction": {
            "hover": true,
            "tooltipDelay": 200
        }
    }
    """)

    # Add nodes and build metadata labels for focus mode
    node_detail_labels = {}  # nid -> multi-line detail label (for focus mode)
    node_urls = {}  # nid -> URL (for clickable links)
    for nid, attrs in kg.g.nodes(data=True):
        node_type = attrs.get("node_type", "unknown")
        name = attrs.get("name", nid)
        color = COLORS.get(node_type, "#CCCCCC")

        # Size based on connectivity
        degree = kg.g.degree(nid)
        size = max(10, min(50, 8 + degree * 3))

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

        # Build tooltip (HTML for hover popup)
        name_html = f'<a href="{url}" target="_blank" style="color:inherit;text-decoration:underline;">{name}</a>' if url else name
        title_parts = [f"<b>{name_html}</b> ({node_type})"]
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
            font={"size": 14, "color": "#000000"},
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

        net.add_edge(src, dst, color=color, title=title, arrows="to", width=1)

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

    net.save_graph(str(output_path))

    # Build the edge-dates JS data and inject timeline + legend into HTML
    html = output_path.read_text()

    inject = _build_timeline_and_legend_html(
        edge_dates, min_year, max_year, node_detail_labels, edge_detail_labels, node_urls
    )
    html = html.replace("</body>", inject + "</body>")
    output_path.write_text(html)

    return output_path


def _build_timeline_and_legend_html(
    edge_dates: dict[str, int],
    min_year: int,
    max_year: int,
    node_detail_labels: dict[str, str],
    edge_detail_labels: dict[str, str],
    node_urls: dict[str, str],
) -> str:
    """Build the HTML/CSS/JS for the timeline slider, legend, and interactions."""
    edge_dates_json = json.dumps(edge_dates)
    node_labels_json = json.dumps(node_detail_labels, ensure_ascii=False)
    edge_labels_json = json.dumps(edge_detail_labels, ensure_ascii=False)
    node_urls_json = json.dumps(node_urls, ensure_ascii=False)

    return f"""
<!-- Legend -->
<div id="graph-legend" style="
    position: fixed;
    bottom: 80px;
    right: 20px;
    background: rgba(255,255,255,0.95);
    border: 1px solid #ccc;
    border-radius: 8px;
    padding: 12px 16px;
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif;
    font-size: 13px;
    box-shadow: 0 2px 8px rgba(0,0,0,0.15);
    z-index: 9999;
    line-height: 1.6;
">
    <div style="font-weight: 600; margin-bottom: 6px; font-size: 14px;">Legend</div>
    <div><span style="display:inline-block;width:12px;height:12px;border-radius:50%;background:#4A90D9;margin-right:6px;vertical-align:middle;"></span>VC Firm</div>
    <div><span style="display:inline-block;width:12px;height:12px;border-radius:50%;background:#50C878;margin-right:6px;vertical-align:middle;"></span>Company</div>
    <div><span style="display:inline-block;width:12px;height:12px;border-radius:50%;background:#FF8C42;margin-right:6px;vertical-align:middle;"></span>Person</div>
    <hr style="margin:6px 0;border:none;border-top:1px solid #eee;">
    <div><span style="display:inline-block;width:16px;height:2px;background:#888888;margin-right:6px;vertical-align:middle;"></span>Invested in</div>
    <div><span style="display:inline-block;width:16px;height:2px;background:#CC8800;margin-right:6px;vertical-align:middle;"></span>Partner at</div>
    <div><span style="display:inline-block;width:16px;height:2px;background:#DD6644;margin-right:6px;vertical-align:middle;"></span>Personal inv.</div>
</div>

<!-- Timeline Bar -->
<style>
    #timeline-bar {{
        position: fixed;
        bottom: 0; left: 0; right: 0;
        background: rgba(255,255,255,0.97);
        border-top: 1px solid #ccc;
        padding: 12px 24px 16px;
        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif;
        font-size: 13px;
        z-index: 9999;
        box-shadow: 0 -2px 8px rgba(0,0,0,0.1);
    }}
    .range-slider {{
        position: relative;
        height: 28px;
        flex: 1;
    }}
    .range-slider .track {{
        position: absolute;
        top: 12px; left: 0; right: 0;
        height: 4px;
        background: #ddd;
        border-radius: 2px;
    }}
    .range-slider .highlight {{
        position: absolute;
        top: 12px;
        height: 4px;
        background: #4A90D9;
        border-radius: 2px;
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
        width: 18px; height: 18px;
        border-radius: 50%;
        background: #4A90D9;
        border: 2px solid #fff;
        box-shadow: 0 1px 4px rgba(0,0,0,0.3);
        cursor: pointer;
        pointer-events: auto;
    }}
    .range-slider input[type=range]::-moz-range-thumb {{
        width: 18px; height: 18px;
        border-radius: 50%;
        background: #4A90D9;
        border: 2px solid #fff;
        box-shadow: 0 1px 4px rgba(0,0,0,0.3);
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
        font-size: 10px;
        color: #999;
        min-width: 0;
        text-align: center;
    }}
</style>
<div id="timeline-bar">
    <div style="display:flex; align-items:center; gap:14px; max-width:1200px; margin:0 auto;">
        <span style="font-weight:600; white-space:nowrap;">Timeline</span>
        <span id="year-min-label" style="min-width:36px; text-align:right; font-variant-numeric:tabular-nums; font-weight:500;">{min_year}</span>
        <div class="range-slider">
            <div class="track"></div>
            <div class="highlight" id="range-highlight"></div>
            <input type="range" id="year-min" min="{min_year}" max="{max_year}" value="{min_year}">
            <input type="range" id="year-max" min="{min_year}" max="{max_year}" value="{max_year}">
        </div>
        <span id="year-max-label" style="min-width:36px; font-variant-numeric:tabular-nums; font-weight:500;">{max_year}</span>
        <span id="timeline-info" style="color:#666; white-space:nowrap; min-width:140px;"></span>
        <button id="timeline-reset" style="
            padding: 4px 12px; border: 1px solid #ccc; border-radius: 4px;
            background: #f5f5f5; cursor: pointer; font-size: 12px; white-space: nowrap;
        ">Reset</button>
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
                    nodeUpdates.push({{ id: n.id, hidden: false, opacity: 0.1, color: '#e0e0e0' }});
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
        background: rgba(255,255,255,0.97);
        border: 1px solid #ccc;
        border-radius: 6px;
        padding: 8px 12px;
        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif;
        font-size: 13px;
        line-height: 1.5;
        box-shadow: 0 2px 8px rgba(0,0,0,0.15);
        max-width: 400px;
        color: #333;
        pointer-events: auto;
        z-index: 10000;
    }}
    #custom-tooltip a {{
        color: #1a6dca;
        text-decoration: underline;
    }}
    #custom-tooltip a:hover {{
        color: #0d4d8b;
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
    // Detail labels for focus mode
    var nodeDetailLabels = {node_labels_json};
    var edgeDetailLabels = {edge_labels_json};

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
                if (n.id === nodeId) {{
                    nodeUpdates.push({{
                        id: n.id,
                        label: nodeDetailLabels[n.id] || origNode[n.id].label,
                        size: Math.max(40, (origNode[n.id].size || 15) * 2.5),
                        color: {{ background: origNode[n.id].color, border: '#333' }},
                        borderWidth: 3,
                        shape: 'box',
                        font: {{ size: 22, color: '#000', face: 'arial', multi: false, align: 'center', strokeWidth: 0 }},
                        opacity: 1
                    }});
                }} else if (neighborSet.has(n.id)) {{
                    nodeUpdates.push({{
                        id: n.id,
                        label: nodeDetailLabels[n.id] || origNode[n.id].label,
                        size: Math.max(30, (origNode[n.id].size || 15) * 1.5),
                        color: {{ background: origNode[n.id].color, border: '#666' }},
                        borderWidth: 2,
                        shape: 'box',
                        font: {{ size: 18, color: '#222', face: 'arial', multi: false, align: 'center', strokeWidth: 0 }},
                        opacity: 1
                    }});
                }} else {{
                    nodeUpdates.push({{
                        id: n.id,
                        label: '',
                        size: origNode[n.id].size,
                        color: '#e8e8e8',
                        borderWidth: 0,
                        shape: origNode[n.id].shape,
                        font: {{ color: 'rgba(0,0,0,0)' }},
                        opacity: 0.08
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
                        font: {{ size: 16, color: '#000', strokeWidth: 0, align: 'top' }},
                        hidden: false
                    }});
                }} else {{
                    edgeUpdates.push({{
                        id: e.id,
                        color: 'rgba(220,220,220,0.1)',
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
"""


def main():
    output = generate_html()
    print(f"Generated visualization at: {output}")


if __name__ == "__main__":
    main()
