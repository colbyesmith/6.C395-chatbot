"""
SAMHSA Treatment Locator – Gradio app for HuggingFace Spaces.

Two-pane layout: map (left) + chat (right). When GOOGLE_MAPS_API_KEY is set in .env,
the map uses Google Maps (JavaScript API); otherwise Folium/OpenStreetMap.
Facility markers and search results are shown on the map.
"""

import base64
import html as html_module
import json
import os
import time

import folium
import gradio as gr
import requests

# Load .env from project root so GOOGLE_MAPS_API_KEY is set regardless of launch cwd
_APP_DIR = os.path.dirname(os.path.abspath(__file__))
_ENV_PATH = os.path.join(_APP_DIR, ".env")
try:
    from dotenv import load_dotenv
    load_dotenv(_ENV_PATH)
except ImportError:
    pass

from src.chat import DEFAULT_STATE, Chatbot

# Use Google Maps when key is set; otherwise Folium/OSM. Enable "Maps JavaScript API" in Google Cloud.
GOOGLE_MAPS_API_KEY = (os.environ.get("GOOGLE_MAPS_API_KEY") or "").strip() or None
if not GOOGLE_MAPS_API_KEY and os.path.isfile(_ENV_PATH):
    with open(_ENV_PATH) as f:
        for line in f:
            line = line.strip()
            if line.startswith("GOOGLE_MAPS_API_KEY=") and "=" in line:
                key = line.split("=", 1)[1].strip().strip('"').strip("'")
                if key:
                    GOOGLE_MAPS_API_KEY = key
                break

# City/place -> (lat, lon) for map pins (fast lookup). Add more as needed.
CITY_COORDS = {
    "boston": (42.36, -71.06),
    "belmont": (42.40, -71.18),
    "roxbury": (42.33, -71.08),
    "allston": (42.35, -71.13),
    "amesbury": (42.86, -70.93),
    "austin": (30.27, -97.74),
    "san antonio": (29.42, -98.49),
    "san francisco": (37.77, -122.42),
    "los angeles": (34.05, -118.25),
    "lake view terrace": (34.27, -118.37),
    "chicago": (41.88, -87.63),
}
# Geocode cache so any city/state from search results can be shown on the map.
_GEOCODE_CACHE = {}
# Show all proposed facilities (chat returns up to 5; allow more for geocoding).
_MAX_GEOCODE_PER_MAP = 20

MAP_HEIGHT_PX = 420


def _geocode(location_str):
    """Resolve address/city to (lat, lon) using Nominatim. Returns None on failure. Uses cache."""
    if not location_str or not location_str.strip():
        return None
    key = location_str.strip().lower()
    if key in _GEOCODE_CACHE:
        return _GEOCODE_CACHE[key]
    try:
        from geopy.geocoders import Nominatim
        from geopy.extra.rate_limiter import RateLimiter
        geocoder = Nominatim(user_agent="samhsa-treatment-locator")
        geocode = RateLimiter(geocoder.geocode, min_delay_seconds=1.0)
        result = geocode(location_str.strip(), country_codes="us")
        if result:
            coord = (result.latitude, result.longitude)
            _GEOCODE_CACHE[key] = coord
            return coord
    except Exception:
        pass
    return CITY_COORDS.get(key)


def _decode_google_polyline(encoded: str):
    """Decode Google's encoded polyline string to list of (lat, lon)."""
    # https://developers.google.com/maps/documentation/utilities/polylinealgorithm
    coords = []
    i = 0
    lat = 0
    lon = 0
    while i < len(encoded):
        b = 0
        shift = 0
        result = 0
        while True:
            b = ord(encoded[i]) - 63
            i += 1
            result |= (b & 0x1F) << shift
            shift += 5
            if b < 0x20:
                break
        dlat = ~(result >> 1) if result & 1 else result >> 1
        lat += dlat
        shift = 0
        result = 0
        while True:
            b = ord(encoded[i]) - 63
            i += 1
            result |= (b & 0x1F) << shift
            shift += 5
            if b < 0x20:
                break
        dlon = ~(result >> 1) if result & 1 else result >> 1
        lon += dlon
        coords.append((lat * 1e-5, lon * 1e-5))
    return coords


def _get_route(lat1, lon1, lat2, lon2):
    """Return list of (lat, lon) for driving route. Uses Google Directions if GOOGLE_MAPS_API_KEY set, else OSRM."""
    if GOOGLE_MAPS_API_KEY:
        try:
            url = (
                "https://maps.googleapis.com/maps/api/directions/json"
                f"?origin={lat1},{lon1}&destination={lat2},{lon2}&key={GOOGLE_MAPS_API_KEY}"
            )
            r = requests.get(url, timeout=10)
            if r.status_code != 200:
                return _get_route_osrm(lat1, lon1, lat2, lon2)
            data = r.json()
            if data.get("status") != "OK" or not data.get("routes"):
                return _get_route_osrm(lat1, lon1, lat2, lon2)
            points = data["routes"][0].get("overview_polyline", {}).get("points")
            if points:
                return _decode_google_polyline(points)
        except Exception:
            pass
        return _get_route_osrm(lat1, lon1, lat2, lon2)
    return _get_route_osrm(lat1, lon1, lat2, lon2)


def _get_route_osrm(lat1, lon1, lat2, lon2):
    """Return list of (lat, lon) for driving route from OSRM (free), or None."""
    try:
        url = (
            "https://router.project-osrm.org/route/v1/driving/"
            f"{lon1},{lat1};{lon2},{lat2}?overview=full&geometries=geojson"
        )
        r = requests.get(url, timeout=5)
        if r.status_code != 200:
            return None
        data = r.json()
        if not data.get("routes"):
            return None
        coords = data["routes"][0]["geometry"]["coordinates"]
        return [(c[1], c[0]) for c in coords]
    except Exception:
        return None


def _facility_coord(f, geocode_count=None):
    """(lat, lon) for a facility: CITY_COORDS first, then geocode city+state (cached). f uses CSV keys."""
    city = (f.get("city") or "").strip()
    state = (f.get("state") or "").strip()
    if not city and not state:
        return None
    city_lower = city.lower()
    state_lower = state.lower()
    coord = CITY_COORDS.get(city_lower) or (CITY_COORDS.get(state_lower) if state_lower else None)
    if coord:
        return coord
    location_str = f"{city}, {state}".strip(", ")
    if not location_str:
        return None
    if geocode_count is not None and len(geocode_count) == 1 and location_str.lower() not in _GEOCODE_CACHE:
        if geocode_count[0] >= _MAX_GEOCODE_PER_MAP:
            return None
        geocode_count[0] += 1
    return _geocode(location_str)


def _popup_html(f):
    """Short HTML for Folium popup. f uses CSV keys (facility_name, address, etc.)."""
    name = f.get("facility_name") or f.get("name") or "Facility"
    addr = f.get("address") or ""
    city = f.get("city") or ""
    st = f.get("state") or ""
    phone = f.get("phone") or ""
    t = f.get("treatment_type") or ""
    parts = [f"<b>{name}</b>", f"{addr}, {city} {st}".strip(", ")]
    if phone:
        parts.append(f"📞 {phone}")
    if t:
        parts.append(f"Type: {t}")
    return "<br>".join(parts)


def _get_facility_coords(facilities):
    """Return list of (lat, lon, facility_dict) for facilities that have coordinates."""
    result = []
    geocode_count = [0]
    for f in facilities:
        if not isinstance(f, dict):
            continue
        coord = _facility_coord(f, geocode_count)
        if coord:
            result.append((coord[0], coord[1], f))
    return result


def _build_google_map_html(facilities, force_update_id=None, selected_facility_name=None):
    """Build Google Maps in an iframe via srcdoc so scripts run (interactive map). Requires GOOGLE_MAPS_API_KEY."""
    if not GOOGLE_MAPS_API_KEY:
        return _build_folium_map_html(facilities, None, force_update_id, selected_facility_name)
    try:
        facility_coords = _get_facility_coords(facilities)
        center_lat, center_lon, zoom = 39.5, -98.5, 3
        if facility_coords:
            lats = [c[0] for c in facility_coords]
            lons = [c[1] for c in facility_coords]
            center_lat = sum(lats) / len(lats)
            center_lon = sum(lons) / len(lons)
            zoom = 10
        markers_data = []
        for lat, lon, f in facility_coords:
            name = (f.get("facility_name") or f.get("name") or "Facility").replace("<", "&lt;").replace(">", "&gt;")
            info = _popup_html(f)
            sel = selected_facility_name and (f.get("facility_name") or f.get("name") or "") == selected_facility_name
            markers_data.append({"lat": lat, "lng": lon, "name": name, "info": info, "selected": sel})
        # Base64-encode markers so srcdoc HTML escaping cannot break the JSON
        markers_json = json.dumps(markers_data)
        markers_b64 = base64.b64encode(markers_json.encode("utf-8")).decode("ascii")
        script_url = f"https://maps.googleapis.com/maps/api/js?key={GOOGLE_MAPS_API_KEY}&callback=init"
        doc = f"""<!DOCTYPE html><html><head><meta charset="utf-8"></head><body style="margin:0">
<div id="map" style="width:100%;height:100%;min-height:{MAP_HEIGHT_PX}px;"></div>
<script>
var center = {{ lat: {center_lat}, lng: {center_lon} }};
var zoom = {zoom};
var markersData = JSON.parse(atob("{markers_b64}"));
function init() {{
  var map = new google.maps.Map(document.getElementById("map"), {{ center: center, zoom: zoom, mapTypeControl: true, fullscreenControl: true, zoomControl: true, scaleControl: true }});
  var infowindow = new google.maps.InfoWindow();
  var bounds = null;
  if (markersData && markersData.length) {{
    markersData.forEach(function(m) {{
      var pos = {{ lat: m.lat, lng: m.lng }};
      var opts = {{ position: pos, map: map, title: m.name }};
      if (m.selected) {{
        opts.icon = {{ path: google.maps.SymbolPath.CIRCLE, scale: 14, fillColor: "#c62828", fillOpacity: 1, strokeColor: "#fff", strokeWeight: 3 }};
      }}
      var marker = new google.maps.Marker(opts);
      marker.addListener("click", function() {{ infowindow.setContent(m.info); infowindow.open(map, marker); }});
      if (!bounds) bounds = new google.maps.LatLngBounds(pos, pos);
      else bounds.extend(pos);
    }});
    if (bounds && markersData.length > 0) {{
      map.fitBounds(bounds, {{ top: 40, right: 40, bottom: 40, left: 40 }});
      if (markersData.length === 1) map.setZoom(12);
    }}
  }}
}}
</script>
<script src="{script_url}" async defer></script>
</body></html>"""
        # Embed in iframe via srcdoc so the document runs in its own context and scripts execute
        escaped = html_module.escape(doc, quote=True)
        html = f'<iframe srcdoc="{escaped}" style="width:100%;height:{MAP_HEIGHT_PX}px;border:0;border-radius:12px;" title="Google Map"></iframe>'
        if force_update_id is not None:
            html += f"<!-- map-update:{force_update_id} -->"
        return html
    except Exception as e:
        return (
            f'<div style="width:100%;height:{MAP_HEIGHT_PX}px;display:flex;align-items:center;justify-content:center;'
            f'background:#f5f5f5;border-radius:12px;color:#666;">'
            f'Map could not be loaded. ({str(e)[:80]})</div>'
        )


def _build_map_html(facilities, user_location_str=None, force_update_id=None, selected_facility_name=None):
    """Build map HTML: Google Maps (iframe) when key is set, else Folium/OSM."""
    if GOOGLE_MAPS_API_KEY:
        return _build_google_map_html(facilities, force_update_id, selected_facility_name)
    return _build_folium_map_html(facilities, user_location_str, force_update_id, selected_facility_name)


def _build_folium_map_html(facilities, user_location_str=None, force_update_id=None, selected_facility_name=None):
    """
    Build Folium (Leaflet) map as HTML. Scroll over map to zoom, drag to pan.
    If user_location_str is set, center on it and show a route to the first facility.
    selected_facility_name: if set, the matching facility is shown with a red star icon.
    force_update_id: optional unique value (e.g. timestamp) so Gradio re-renders the HTML each time.
    Returns safe fallback HTML on any error.
    """
    try:
        center_lat, center_lon, zoom = 39.5, -98.5, 3
        user_lat_lon = _geocode(user_location_str) if user_location_str else None
        facility_coords = [(c[0], c[1], c[2]) for c in _get_facility_coords(facilities)]
        facility_coords = [((c[0], c[1]), c[2]) for c in facility_coords]

        if user_lat_lon:
            center_lat, center_lon = user_lat_lon
            zoom = 11
        elif facility_coords:
            lats = [c[0] for c, _ in facility_coords]
            lons = [c[1] for c, _ in facility_coords]
            center_lat = sum(lats) / len(lats)
            center_lon = sum(lons) / len(lons)
            zoom = 10

        m = folium.Map(
            location=[center_lat, center_lon],
            zoom_start=zoom,
            tiles="OpenStreetMap",
            control_scale=True,
            zoom_control=True,
        )
        m.options["scrollWheelZoom"] = True
        m.options["touchZoom"] = True
        m.options["dragging"] = True

        if user_lat_lon:
            folium.Marker(
                user_lat_lon,
                popup="You",
                tooltip="Your location",
                icon=folium.Icon(color="blue", icon="info-sign"),
            ).add_to(m)
        if user_lat_lon and facility_coords:
            dest_lat, dest_lon = facility_coords[0][0][0], facility_coords[0][0][1]
            route = _get_route(user_lat_lon[0], user_lat_lon[1], dest_lat, dest_lon)
            if route:
                folium.PolyLine(route, color="teal", weight=4, opacity=0.8).add_to(m)

        for (lat, lon), f in facility_coords:
            is_selected = selected_facility_name and (f.get("facility_name") or f.get("name") or "") == selected_facility_name
            folium.Marker(
                [lat, lon],
                popup=folium.Popup(_popup_html(f), max_width=280),
                tooltip=f.get("facility_name") or f.get("name") or "Facility",
                icon=folium.Icon(color="red" if is_selected else "green", icon="star" if is_selected else "plus-sign"),
            ).add_to(m)

        # Center and zoom to show all proposed locations
        if facility_coords:
            lats = [c[0] for c, _ in facility_coords]
            lons = [c[1] for c, _ in facility_coords]
            sw = [min(lats), min(lons)]
            ne = [max(lats), max(lons)]
            # Avoid zero-size bounds (single marker): add small buffer
            buf = 0.01
            if ne[0] - sw[0] < buf:
                sw[0] -= buf
                ne[0] += buf
            if ne[1] - sw[1] < buf:
                sw[1] -= buf
                ne[1] += buf
            m.fit_bounds([sw, ne])

        html = m._repr_html_()
        wrapper = f'<div style="width:100%;height:{MAP_HEIGHT_PX}px;overflow:hidden;border-radius:12px;">{html}</div>'
        # Force Gradio to re-render: append a unique comment so the value always changes
        if force_update_id is not None:
            wrapper += f"<!-- map-update:{force_update_id} -->"
        return wrapper
    except Exception as e:
        return (
            f'<div style="width:100%;height:{MAP_HEIGHT_PX}px;display:flex;align-items:center;justify-content:center;'
            f'background:#f5f5f5;border-radius:12px;color:#666;font-family:sans-serif;">'
            f'Map could not be loaded. ({str(e)[:80]})</div>'
        )

DISCLAIMER = (
    "**Disclaimer:** Information is from SAMHSA data. Always verify with the facility or "
    "[findtreatment.gov](https://findtreatment.gov) before making decisions. This tool does not endorse any facility."
)

DESCRIPTION = (
    "Find treatment facilities by chatting: say where you are (city or state), what type of care you need, "
    "and payment (e.g. Medicaid, insurance). Results show on the map. Data from SAMHSA only."
)

EXAMPLES = [
    "I'm looking for outpatient alcohol treatment in Boston with Medicaid.",
    "Do you have options for veterans in Texas?",
    "Hi, I need help finding a residential program in California that accepts Medicaid.",
]

CSS = """
.disclaimer { font-size: 0.85em; color: #555; padding: 0.5rem 0.75rem; background: #f8f9fa; border-radius: 8px; margin-bottom: 0.75rem; }
.map-pane { padding: 0.25rem 0 0 0; }
.map-pane .map-html { border-radius: 12px; overflow: hidden; box-shadow: 0 2px 12px rgba(0,0,0,0.08); }
.map-pane iframe { border-radius: 12px; }
.try-label { font-size: 0.9em; margin-bottom: 0.25rem; }
"""


def _messages_to_tuples(history):
    """Convert Gradio 6 messages format to [(user, assistant), ...] for get_response."""
    if not history:
        return []
    out = []
    for item in history:
        if isinstance(item, (list, tuple)) and len(item) >= 2:
            out.append([item[0], item[1]])
        elif isinstance(item, dict):
            role, content = item.get("role"), item.get("content", "")
            if role == "user":
                out.append([content, ""])
            elif role == "assistant":
                if out:
                    out[-1][1] = content
                else:
                    out.append(["", content])
        else:
            out.append(["", str(item)])
    return out


def _tuples_to_messages(history):
    """Convert [(user, assistant), ...] to Gradio 6 messages format."""
    out = []
    for user_msg, assistant_msg in history or []:
        if user_msg:
            out.append({"role": "user", "content": user_msg})
        if assistant_msg:
            out.append({"role": "assistant", "content": assistant_msg})
    return out


def create_demo():
    chatbot = Chatbot()

    with gr.Blocks(title="SAMHSA Treatment Locator", css=CSS) as demo:
        gr.Markdown("# SAMHSA Treatment Locator")
        gr.Markdown(DESCRIPTION)
        gr.Markdown(f"<div class='disclaimer'>{DISCLAIMER}</div>", elem_classes=["disclaimer"])

        state = gr.State(DEFAULT_STATE)

        with gr.Row():
            # Left: Folium (Leaflet) map — scroll over map to zoom, drag to pan
            with gr.Column(scale=5, min_width=320, elem_classes=["map-pane"]):
                gr.Markdown("**Map** — scroll over map to zoom, drag to pan. Search in chat to see facilities.")
                map_html = gr.HTML(
                    value=_build_map_html([], None),
                    elem_classes=["map-html"],
                )
            # Right: chat
            with gr.Column(scale=5, min_width=320):
                gr.Markdown("**Chat** — tell me location, treatment type, and payment.")
                _chat_kw = {
                    "label": "Conversation",
                    "placeholder": "E.g. I'm in Boston, need outpatient treatment with Medicaid.",
                    "height": 420,
                    "show_label": False,
                }
                if "type" in __import__("inspect").signature(gr.Chatbot).parameters:
                    _chat_kw["type"] = "messages"
                chat = gr.Chatbot(**_chat_kw)
                facility_dropdown = gr.Dropdown(
                    choices=[],
                    value=None,
                    label="Choose a treatment center (pin updates on map)",
                    allow_custom_value=False,
                )
                with gr.Row():
                    msg = gr.Textbox(
                        placeholder="Type a message…",
                        show_label=False,
                        container=False,
                        scale=8,
                    )
                    submit_btn = gr.Button("Send", variant="primary", scale=1)
                gr.Markdown("**Try:**", elem_classes=["try-label"])
                gr.Examples(
                    examples=EXAMPLES,
                    inputs=msg,
                    label=None,
                    examples_per_page=6,
                )

        def _facility_names(facilities):
            return [f.get("facility_name") or f.get("name") or "Facility" for f in facilities]

        def user_submit(message, history, state):
            update_id = str(time.time())
            if not message or not message.strip():
                facilities = list(state.get("last_results") or [])
                sel = state.get("selected_facility_name")
                map_html_out = _build_map_html(facilities, None, update_id, sel)
                return history, state, "", map_html_out, gr.update(choices=_facility_names(facilities))
            try:
                history_tuples = _messages_to_tuples(history)
                reply, new_state = chatbot.get_response(message, history_tuples, state)
                new_state = dict(new_state)
                new_state["selected_facility_name"] = None  # clear selection when new results
                new_history_tuples = history_tuples + [[message, reply]]
                new_history_messages = _tuples_to_messages(new_history_tuples)
                facilities = list(new_state.get("last_results") or [])
                map_html_out = _build_map_html(facilities, None, update_id, None)
                return new_history_messages, new_state, "", map_html_out, gr.update(choices=_facility_names(facilities), value=None)
            except Exception as e:
                err_msg = str(e)[:200]
                reply = f"Sorry, something went wrong: {err_msg}"
                if "token" in err_msg.lower() or "auth" in err_msg.lower():
                    reply += " Check that HF_TOKEN is set in .env for the chat model."
                history_tuples = _messages_to_tuples(history)
                new_history_tuples = history_tuples + [[message, reply]]
                new_history_messages = _tuples_to_messages(new_history_tuples)
                facilities = list(state.get("last_results") or [])
                sel = state.get("selected_facility_name")
                map_html_out = _build_map_html(facilities, None, update_id, sel)
                return new_history_messages, state, "", map_html_out, gr.update()

        def on_facility_select(choice, state):
            if not choice:
                state = dict(state or {})
                state["selected_facility_name"] = None
                facilities = list(state.get("last_results") or [])
                map_html_out = _build_map_html(facilities, None, str(time.time()), None)
                return map_html_out, state
            state = dict(state or {})
            state["selected_facility_name"] = choice
            facilities = list(state.get("last_results") or [])
            map_html_out = _build_map_html(facilities, None, str(time.time()), choice)
            return map_html_out, state

        submit_btn.click(
            user_submit,
            inputs=[msg, chat, state],
            outputs=[chat, state, msg, map_html, facility_dropdown],
        )
        msg.submit(
            user_submit,
            inputs=[msg, chat, state],
            outputs=[chat, state, msg, map_html, facility_dropdown],
        )
        facility_dropdown.change(
            on_facility_select,
            inputs=[facility_dropdown, state],
            outputs=[map_html, state],
        )

    return demo


if __name__ == "__main__":
    import inspect
    demo = create_demo()
    sig = inspect.signature(demo.launch)
    kwargs = {}
    if "theme" in sig.parameters and hasattr(gr, "themes"):
        kwargs["theme"] = gr.themes.Soft(primary_hue="teal", secondary_hue="slate")
    demo.launch(**kwargs)
