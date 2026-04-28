import streamlit as st
import plotly.graph_objects as go
from PIL import Image
import networkx as nx
from hospital_router import build_hospital_graph, find_optimized_paths 

# ==========================================
# PAGE CONFIGURATION
# ==========================================
st.set_page_config(page_title="Hospital Wayfinder", layout="wide")

st.title("🏥 Smart Hospital Wayfinding System")
st.markdown("### Interactive Decision-Support Dashboard")

# ==========================================
# CACHE THE ALGORITHM
# ==========================================
@st.cache_resource
def load_hospital_data():
    # Ensure 'new block.dxf' is in your GitHub root directory
    return build_hospital_graph("new block.dxf")

with st.spinner("Loading structural network geometry..."):
    net, db = load_hospital_data()

# ==========================================
# THE CALIBRATED MULTI-FLOOR DICTIONARY
# ==========================================
# These are the precise bounds you extracted via X-Ray mode
# The Master Bounding Box from AutoCAD (applies to ALL floors)
MASTER_WEST = 417942.2
MASTER_EAST = 532554.5
MASTER_SOUTH = -157112.6
MASTER_NORTH = -145093.6
MASTER_BOUNDS = [MASTER_WEST, MASTER_EAST, MASTER_SOUTH, MASTER_NORTH]

floor_data = {
    "Lower Ground (LG)": {"img": "new block-LG_EXPORT.png", "bounds": MASTER_BOUNDS},
    "Upper Ground (UG)": {"img": "new block-UG_EXPORT.png", "bounds": MASTER_BOUNDS},
    "2nd Floor (2F)": {"img": "new block-2F_EXPORT.png", "bounds": MASTER_BOUNDS},
    "3rd Floor (3F)": {"img": "new block-3F_EXPORT.png", "bounds": MASTER_BOUNDS},
    "4th Floor (4F)": {"img": "new block-4F_EXPORT.png", "bounds": MASTER_BOUNDS},
    "5th Floor (5F)": {"img": "new block-5F_EXPORT.png", "bounds": MASTER_BOUNDS},
    "6th Floor (6F)": {"img": "new block-6F_EXPORT.png", "bounds": MASTER_BOUNDS}
}

# ==========================================
# THE INTERACTIVE USER INTERFACE
# ==========================================
if net and db:
    all_rooms = sorted(list(db.keys()))
    
    with st.sidebar:
        st.header("Navigation Parameters")
        
        role_options = ["DOCTOR", "STAFF", "PATIENT", "VISITOR", "PWD"]
        user_role = st.selectbox("👤 Security Clearance:", options=role_options, index=3)
        st.divider()
        start_point = st.selectbox("📍 Current Location:", options=all_rooms, index=0)
        destination = st.selectbox("🏁 Destination:", options=all_rooms, index=1)
        st.divider()
        calculate_btn = st.button("Calculate Optimal Route", type="primary", use_container_width=True)

    # Floor Selector (Moved outside the IF block to prevent NameErrors)
    st.markdown("---")
    view_floor = st.selectbox("👁️ View Floor Map:", options=list(floor_data.keys()), index=1)

    if calculate_btn:
        if start_point == destination:
            st.warning("You are already at your destination!")
        else:
            with st.spinner("Calculating multi-objective trade-offs..."):
                result = find_optimized_paths(net, db, start_point, destination, user_role)
                
                text_col, map_col = st.columns([1, 2])
                
                with text_col:
                    st.markdown("### Recommended Itinerary")
                    st.success("Routing Complete.")
                    st.code(result, language="markdown")
                
                with map_col:
                    st.markdown(f"### 🗺️ Structural Spatial Map: {view_floor}")
                    
                    fig = go.Figure()
                    
                    try:
                        selected_floor = floor_data[view_floor]
                        img_path = selected_floor["img"]
                        dx_min, dx_max, dy_min, dy_max = selected_floor["bounds"]
                        
                        img = Image.open(img_path)
                        
                        # 1. Image Pixel Dimensions
                        img_w = img.width
                        img_h = img.height
                        img_ratio = img_w / img_h
                        
                        # 2. AutoCAD Math Dimensions
                        cad_w = dx_max - dx_min
                        cad_h = dy_max - dy_min
                        
                        # 3. True Height Calculation
                        true_image_height = cad_w / img_ratio
                        
                        # ==========================================
                        # MICRO-NUDGE OFFSETS FOR ALIGNMENT
                        # ==========================================
                        # Adjust these numbers to slide the image under the route!
                        # Positive x_offset moves image RIGHT, Negative moves LEFT
                        # Positive y_offset moves image UP, Negative moves DOWN
                        
                        x_offset = 200   # Sliding image left slightly
                        y_offset = -200   # Sliding image down slightly
                        
                        # Apply the offsets
                        y_center = dy_min + (cad_h / 2)
                        y_adjusted_max = y_center + (true_image_height / 2) + float(y_offset)
                        x_adjusted_min = dx_min + float(x_offset)
                        
                        # 4. Draw the perfectly proportioned, shifted image
                        fig.add_layout_image(
                            dict(
                                source=img,
                                xref="x", yref="y",
                                x=x_adjusted_min, y=y_adjusted_max,
                                sizex=cad_w,
                                sizey=true_image_height,
                                sizing="stretch", 
                                opacity=0.9,
                                layer="below"
                            )
                        )

                        if "SEQUENCE LIST" in result:
                            s_node = db[start_point]
                            e_node = db[destination]
                            try:
                                path = nx.shortest_path(net, s_node, e_node, weight='weight')
                                
                                # MULTI-FLOOR FILTER
                                floor_path_x = []
                                floor_path_y = []
                                
                                for p in path:
                                    if (dx_min - 500) <= p[0] <= (dx_max + 500) and (dy_min - 500) <= p[1] <= (dy_max + 500):
                                        floor_path_x.append(p[0])
                                        floor_path_y.append(p[1])
                                
                                if len(floor_path_x) > 0:
                                    fig.add_trace(go.Scatter(
                                        x=floor_path_x, y=floor_path_y, 
                                        mode='lines+markers', 
                                        line=dict(color='red', width=6), 
                                        marker=dict(size=8, color='white'),
                                        hoverinfo='skip'
                                    ))
                                    
                                    # Start Marker
                                    if path[0][0] == floor_path_x[0] and path[0][1] == floor_path_y[0]:
                                        fig.add_trace(go.Scatter(
                                            x=[floor_path_x[0]], y=[floor_path_y[0]],
                                            mode='markers+text', text=["📍 START"], textposition="top center",
                                            textfont=dict(size=16, color="white"),
                                            marker=dict(size=20, color='#00cc66', line=dict(width=3, color='white'))
                                        ))
                                        
                                    # End Marker
                                    if path[-1][0] == floor_path_x[-1] and path[-1][1] == floor_path_y[-1]:
                                        fig.add_trace(go.Scatter(
                                            x=[floor_path_x[-1]], y=[floor_path_y[-1]],
                                            mode='markers+text', text=["🏁 END"], textposition="top center",
                                            textfont=dict(size=16, color="white"),
                                            marker=dict(size=20, color='#3399ff', line=dict(width=3, color='white'))
                                        ))

                            except nx.NetworkXNoPath:
                                pass

                        fig.update_xaxes(range=[dx_min, dx_max], visible=False)
                        fig.update_yaxes(range=[dy_min, dy_max], visible=False, scaleanchor="x", scaleratio=1)
                        
                        fig.update_layout(
                            template="plotly_dark", 
                            height=700, 
                            margin=dict(l=0, r=0, b=0, t=0), 
                            dragmode='pan', 
                            showlegend=False
                        )
                        st.plotly_chart(fig, use_container_width=True)
                        
                    except Exception as e:
                        st.error(f"Mapping Error: {e}")
else:
    st.error("System Offline: Could not load the hospital map data.")
