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
                    st.markdown(f"### 🗺️ Topological Network: {view_floor}")
                    
                    try:
                        x0, x1, y0, y1 = floor_data[view_floor]["bounds"]
                        floor_width = x1 - x0
                        floor_height = y1 - y0
                        
                        # ==========================================
                        # THE NUCLEAR FIX: MIN-MAX SCALING (0 to 100)
                        # ==========================================
                        def scale_x(val): 
                            return ((val - x0) / floor_width) * 100 if floor_width != 0 else 50
                        
                        def scale_y(val): 
                            return ((val - y0) / floor_height) * 100 if floor_height != 0 else 50

                        fig = go.Figure()

                        # 1. GATHER AND SCALE FLOOR NODES
                        floor_nodes_x, floor_nodes_y, floor_node_names = [], [], []
                        
                        for name, pos in db.items():
                            # Only grab nodes that actually belong on this specific floor
                            if x0 <= pos[0] <= x1 and y0 <= pos[1] <= y1:
                                floor_nodes_x.append(scale_x(pos[0]))
                                floor_nodes_y.append(scale_y(pos[1]))
                                
                                if any(kw in name for kw in ["STAIR", "ELEV", "LOBBY", "ROOM", "WARD", "PHARMACY"]):
                                    floor_node_names.append(name)
                                else:
                                    floor_node_names.append("")

                        # 2. DRAW THE SUBWAY NODES
                        fig.add_trace(go.Scatter(
                            x=floor_nodes_x, y=floor_nodes_y,
                            mode='markers+text',
                            marker=dict(size=12, color='#2c3e50', line=dict(width=1, color='#7f8c8d')),
                            text=floor_node_names,
                            textposition="bottom center",
                            textfont=dict(size=10, color="#bdc3c7"),
                            hoverinfo="text",
                            name="Locations"
                        ))

                        # 3. DRAW AND SCALE THE OPTIMAL ROUTE
                        if "SEQUENCE LIST" in result:
                            s_node, e_node = db[start_point], db[destination]
                            try:
                                path = nx.shortest_path(net, s_node, e_node, weight='weight')
                                
                                # Filter the path to ONLY show the parts that are on THIS floor
                                # (This prevents routes to other floors from breaking the layout!)
                                path_on_floor = [p for p in path if x0 <= p[0] <= x1 and y0 <= p[1] <= y1]
                                
                                if path_on_floor:
                                    rx = [scale_x(p[0]) for p in path_on_floor]
                                    ry = [scale_y(p[1]) for p in path_on_floor]
                                    
                                    fig.add_trace(go.Scatter(
                                        x=rx, y=ry, mode='lines+markers', 
                                        line=dict(color='#e74c3c', width=5), 
                                        marker=dict(size=14, color='white', line=dict(width=2, color='#e74c3c')),
                                        name="Optimal Path"
                                    ))
                                    
                                    fig.add_trace(go.Scatter(
                                        x=[rx[0], rx[-1]], y=[ry[0], ry[-1]],
                                        mode='markers+text', text=["📍 START", "🏁 END"], 
                                        textposition="top center",
                                        textfont=dict(size=14, color="white"),
                                        marker=dict(size=18, color=['#2ecc71', '#3498db'])
                                    ))
                            except nx.NetworkXNoPath:
                                pass

                        # 4. LOCK THE GRID TO 0-100
                        fig.update_xaxes(range=[0, 100], showgrid=False, zeroline=False, visible=False)
                        fig.update_yaxes(range=[0, 100], showgrid=False, zeroline=False, visible=False) 
                        
                        fig.update_layout(
                            template="plotly_dark",
                            height=700,
                            margin=dict(l=20, r=20, b=20, t=20),
                            dragmode='pan',
                            showlegend=False
                        )
                        
                        st.plotly_chart(fig, use_container_width=True)
                        
                    except Exception as e:
                        st.error(f"Visualization Error: {e}")
else:
    st.error("System Offline: Could not load the hospital map data.")
