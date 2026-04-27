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
floor_data = {
    "Lower Ground (LG)": {"img": "lg_floor.png", "bounds": [425133.6, 531137.5, -170844.5, -159463.5]},
    "Upper Ground (UG)": {"img": "ug_floor.png", "bounds": [417942.2, 532554.5, -157112.6, -145093.6]},
    "2nd Floor (2F)": {"img": "2f_floor.png", "bounds": [426516.0, 532060.5, -141688.0, -128588.0]},
    "3rd Floor (3F)": {"img": "typ_3f_4f.png", "bounds": [426663.1, 538285.5, -123451.5, -112552.8]},
    "4th Floor (4F)": {"img": "typ_3f_4f.png", "bounds": [425044.6, 530667.0, -109543.5, -98644.7]},
    "5th Floor (5F)": {"img": "5f_floor.png", "bounds": [424336.0, 528224.6, -96369.2, -84121.1]},
    "6th Floor (6F)": {"img": "6f_floor.png", "bounds": [469338.6, 483617.2, -80271.7, -76308.3]}
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
                    st.markdown(f"### 🗺️ Calibrating: {view_floor}")
                    
                    try:
                        selected_floor = floor_data[view_floor]
                        img_path = selected_floor["img"]
                        
                        # 1. THE ZERO-BASE ORIGIN
                        # We use your West and South coordinates as the (0,0) starting point
                        origin_x = selected_floor["bounds"][0] # West
                        origin_y = selected_floor["bounds"][2] # South
                        
                        # ==========================================
                        # LIVE CALIBRATION INPUTS (Lag-Free)
                        # ==========================================
                        st.info("🛠️ **CALIBRATION:** Use the +/- buttons or type a number to fit the map.")
                        col1, col2 = st.columns(2)
                        with col1:
                            # Using number_input instead of slider to prevent continuous re-rendering
                            img_width = st.number_input("↔️ Image Width", min_value=1000, max_value=50000, value=15000, step=250)
                        with col2:
                            img_height = st.number_input("↕️ Image Height", min_value=1000, max_value=50000, value=12000, step=250)
                        
                        fig = go.Figure()
                        img = Image.open(img_path)
                        
                        # 2. PLACE THE IMAGE
                        fig.add_layout_image(
                            dict(
                                source=img,
                                xref="x", yref="y",
                                x=0, y=img_height, # Top-Left corner is now at (0, height)
                                sizex=img_width,
                                sizey=img_height,
                                sizing="stretch",
                                opacity=0.7, # Slightly transparent to see the math grid
                                layer="below"
                            )
                        )

                        # 3. DRAW THE ROUTE (Normalized to 0,0)
                        if "SEQUENCE LIST" in result:
                            s_node, e_node = db[start_point], db[destination]
                            try:
                                path = nx.shortest_path(net, s_node, e_node, weight='weight')
                                
                                # Subtract the origin so the math matches the image perfectly
                                x_coords = [p[0] - origin_x for p in path]
                                y_coords = [p[1] - origin_y for p in path]
                                
                                fig.add_trace(go.Scatter(
                                    x=x_coords, y=y_coords, mode='lines+markers', 
                                    line=dict(color='red', width=6), marker=dict(size=8, color='white')
                                ))
                                
                                # Start and End markers
                                fig.add_trace(go.Scatter(
                                    x=[x_coords[0], x_coords[-1]], y=[y_coords[0], y_coords[-1]],
                                    mode='markers+text', text=["START", "END"], textposition="top center",
                                    marker=dict(size=14, color=['green', 'blue'])
                                ))
                            except nx.NetworkXNoPath:
                                pass

                        # 4. FORCE THE VIEWPORT
                        # This adds 4 invisible dots at the corners of your image.
                        # It FORCES Plotly to frame the image perfectly on your screen.
                        fig.add_trace(go.Scatter(
                            x=[0, img_width, img_width, 0], y=[0, 0, img_height, img_height],
                            mode='markers', marker=dict(color='rgba(0,0,0,0)'), hoverinfo='skip'
                        ))

                        # LOCK THE PROPORTIONS (No Pancakes!)
                        fig.update_xaxes(visible=False)
                        fig.update_yaxes(visible=False, scaleanchor="x", scaleratio=1)
                        
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
