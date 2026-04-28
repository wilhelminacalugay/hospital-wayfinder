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
# CACHE THE ALGORITHM & LOAD DATA
# ==========================================
@st.cache_resource
def load_hospital_data():
    return build_hospital_graph("new block.dxf")

with st.spinner("Loading structural network geometry..."):
    net, db = load_hospital_data()

# ==========================================
# MULTI-FLOOR IMAGE DICTIONARY & BOUNDS
# ==========================================
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
        
        # Select map view in the sidebar so it doesn't reset when the button is clicked
        view_floor = st.selectbox("👁️ View Floor Map:", options=list(floor_data.keys()), index=1)
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
                    st.markdown(f"### Structural Spatial Map: {view_floor}")
                    
                    fig = go.Figure()
                    
                    try:
                        selected_floor = floor_data[view_floor]
                        img_path = selected_floor["img"]
                        dx_min, dx_max, dy_min, dy_max = selected_floor["bounds"]
                        
                        img = Image.open(img_path)
                        
                        # 1. Aspect Ratio Math
                        img_w, img_h = img.width, img.height
                        img_ratio = img_w / img_h
                        
                        cad_w = dx_max - dx_min
                        cad_h = dy_max - dy_min
                        true_image_height = cad_w / img_ratio
                        
                        # 2. Apply your perfect offsets
                        x_offset = 300   
                        y_offset = -140   
                        
                        y_center = dy_min + (cad_h / 2.0)
                        y_adjusted_max = y_center + (true_image_height / 2.0) + float(y_offset)
                        x_adjusted_min = dx_min + float(x_offset)
                        
                        # 3. Draw Background Image
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

                        # 4. Draw the Route
                        if "SEQUENCE LIST" in result:
                            s_node = db[start_point]
                            e_node = db[destination]
                            try:
                                path = nx.shortest_path(net, s_node, e_node, weight='weight')
                                
                                # Multi-Floor Spatial Filter
                                floor_path_x = []
                                floor_path_y = []
                                
                                for p in path:
                                    if (dx_min - 500) <= p[0] <= (dx_max + 500) and (dy_min - 500) <= p[1] <= (dy_max + 500):
                                        floor_path_x.append(p[0])
                                        floor_path_y.append(p[1])
                                
                                if len(floor_path_x) > 0:
                                    # Draw Red Route Line
                                    fig.add_trace(go.Scatter(
                                        x=floor_path_x, y=floor_path_y, 
                                        mode='lines+markers', 
                                        line=dict(color='red', width=6), 
                                        marker=dict(size=8, color='white'),
                                        name="Route",
                                        hoverinfo='skip'
                                    ))
                                    
                                    # Draw Start Marker
                                    if path[0][0] == floor_path_x[0] and path[0][1] == floor_path_y[0]:
                                        fig.add_trace(go.Scatter(
                                            x=[floor_path_x[0]], y=[floor_path_y[0]],
                                            mode='markers+text', text=["📍 START"], textposition="top center",
                                            textfont=dict(size=16, color="white", family="Arial Black"),
                                            marker=dict(size=20, color='#00cc66', line=dict(width=3, color='white')),
                                            name="Start"
                                        ))
                                        
                                    # Draw End Marker
                                    if path[-1][0] == floor_path_x[-1] and path[-1][1] == floor_path_y[-1]:
                                        fig.add_trace(go.Scatter(
                                            x=[floor_path_x[-1]], y=[floor_path_y[-1]],
                                            mode='markers+text', text=["🏁 END"], textposition="top center",
                                            textfont=dict(size=16, color="white", family="Arial Black"),
                                            marker=dict(size=20, color='#3399ff', line=dict(width=3, color='white')),
                                            name="End"
                                        ))

                            except nx.NetworkXNoPath:
                                pass

                        # 5. Lock Camera Bounds
                        fig.update_xaxes(range=[dx_min, dx_max], showgrid=False, zeroline=False, visible=False)
                        fig.update_yaxes(range=[dy_min, dy_max], showgrid=False, zeroline=False, visible=False, scaleanchor="x", scaleratio=1)
                        fig.update_layout(template="plotly_dark", margin=dict(l=0, r=0, t=0, b=0), height=700, showlegend=False, dragmode='pan')
                        
                        st.plotly_chart(fig, use_container_width=True)
                        
                    except FileNotFoundError:
                        st.warning(f"Image '{img_path}' not found on server. Make sure names match exactly!")
else:
    st.error("System Offline: Could not load the hospital map data.")
