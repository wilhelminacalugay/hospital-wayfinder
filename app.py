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
    return build_hospital_graph("new block.dxf")

with st.spinner("Loading structural network geometry..."):
    net, db = load_hospital_data()

# ==========================================
# THE CALIBRATED MULTI-FLOOR DICTIONARY
# ==========================================
floor_data = {
    "Lower Ground (LG)": {"img": "lg_floor.png", "bounds": [422591.4, 530723.7, -168345.7, -161091.0]},
    "Upper Ground (UG)": {"img": "ug_floor.png", "bounds": [425270.6, 504995.7, -151915.6, -146819.8]},
    "2nd Floor (2F)": {"img": "2f_floor.png", "bounds": [423292.6, 529388.5, -141110.1, -128494.5]},
    "3rd Floor (3F)": {"img": "typ_3f_4f.png", "bounds": [423355.6, 531320.6, -121157.7, -112143.0]},
    "4th Floor (4F)": {"img": "typ_3f_4f.png", "bounds": [421737.1, 529702.1, -107249.7, -98234.9]},
    "5th Floor (5F)": {"img": "5f_floor.png", "bounds": [419486.0, 526186.0, -90735.0, -84607.8]},
    "6th Floor (6F)": {"img": "6f_floor.png", "bounds": [468624.7, 484331.1, -80469.9, -76110.1]}
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

    if calculate_btn:
        if start_point == destination:
            st.warning("You are already at your destination!")
        else:
            with st.spinner("Calculating multi-objective trade-offs..."):
                result = find_optimized_paths(net, db, start_point, destination, user_role)
                
                text_col, map_col = st.columns([1, 1.5])
                
                with text_col:
                    st.markdown("### Recommended Itineraries")
                    st.success("Routing Complete.")
                    st.code(result, language="markdown")
                
                with map_col:
                    st.markdown("### Structural Spatial Map")
                    
                    view_floor = st.selectbox("👁️ View Floor Map:", options=list(floor_data.keys()), index=1)
                    fig = go.Figure()
                    
                    try:
                        selected_floor = floor_data[view_floor]
                        img_path = selected_floor["img"]
                        bounds = selected_floor["bounds"]
                        dx_min, dx_max, dy_min, dy_max = bounds[0], bounds[1], bounds[2], bounds[3]
                        
                        img = Image.open(img_path)
                        
                        fig.add_layout_image(
                            dict(
                                source=img,
                                xref="x", yref="y",
                                x=dx_min, y=dy_max,
                                sizex=(dx_max - dx_min),
                                sizey=(dy_max - dy_min),
                                sizing="stretch", # Keep stretch, but we fix the axes below
                                opacity=0.8,
                                layer="below"
                            )
                        )
                        
                        # ==========================================
                        # AUTOSCALE FIX: The Invisible Anchors
                        # ==========================================
                        # These 4 transparent dots sit at the extreme corners of your CAD bounds.
                        # This forces the Autoscale button to frame the whole building, not just the route.
                        fig.add_trace(go.Scatter(
                            x=[dx_min, dx_max, dx_max, dx_min],
                            y=[dy_min, dy_min, dy_max, dy_max],
                            mode='markers',
                            marker=dict(size=1, color='rgba(0,0,0,0)'), # 100% Transparent
                            hoverinfo='skip',
                            showlegend=False
                        ))
                        
                    except FileNotFoundError:
                        st.warning(f"Image '{img_path}' not found on server.")
                        dx_min, dx_max, dy_min, dy_max = 0, 100, 0, 100 

                    # Draw the Optimal Route Line
                    if "SEQUENCE LIST" in result:
                        s_node = db[start_point]
                        e_node = db[destination]
                        try:
                            path = nx.shortest_path(net, s_node, e_node, weight='weight')
                            x_coords = [p[0] for p in path]
                            y_coords = [p[1] for p in path]
                            
                            fig.add_trace(go.Scatter(x=x_coords, y=y_coords, mode='lines+markers', line=dict(color='red', width=5), name="Route"))
                        except nx.NetworkXNoPath:
                            pass

                    # ==========================================
                    # DISTORTION FIX: Axis Locking
                    # ==========================================
                    # scaleanchor and scaleratio force the image to maintain its true geometric shape
                    fig.update_xaxes(range=[dx_min, dx_max], showgrid=False, zeroline=False, visible=False)
                    fig.update_yaxes(range=[dy_min, dy_max], showgrid=False, zeroline=False, visible=False, scaleanchor="x", scaleratio=1)
                    
                    # dragmode='pan' sets the default mouse behavior to moving around rather than drawing selection boxes
                    fig.update_layout(template="plotly_dark", margin=dict(l=0, r=0, t=0, b=0), height=650, showlegend=False, dragmode='pan')
                    
                    st.plotly_chart(fig, use_container_width=True)
else:
    st.error("System Offline: Could not load the hospital map data.")
