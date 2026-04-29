import streamlit as st
import networkx as nx
import plotly.graph_objects as go
from PIL import Image

# Import the logic we built in your backend
from hospital_router import build_hospital_graph, get_restrictions, find_optimized_paths

# ==========================================
# SETUP & CONFIG
# ==========================================
st.set_page_config(page_title="Smart Hospital Wayfinder", layout="wide")
st.title("🏥 Smart Hospital Wayfinding System")

# Define the Master Bounds (Upper Ground)
# [WEST (Min X), EAST (Max X), SOUTH (Min Y), NORTH (Max Y)]
MASTER_BOUNDS = [417942.2, 532554.5, -157112.6, -145093.6]

# ==========================================
# LOAD NETWORK ENGINE
# ==========================================
@st.cache_resource
def load_network():
    # Keep using your original top-to-bottom DXF file for this presentation
    graph, destinations = build_hospital_graph("new block.dxf") 
    return graph, destinations

graph, destinations = load_network()

if graph is None:
    st.error("Failed to load the hospital network. Check your DXF file path.")
    st.stop()

# ==========================================
# USER INTERFACE (SIDEBAR)
# ==========================================
st.sidebar.header("Navigation Setup")

roles = ["PATIENT", "VISITOR", "DOCTOR", "STAFF", "PWD"]
selected_role = st.sidebar.selectbox("Select User Role", roles)

# Sort destinations alphabetically for a clean UI
room_names = sorted(list(destinations.keys()))
start_room = st.sidebar.selectbox("Starting Point", room_names, index=0)
end_room = st.sidebar.selectbox("Destination", room_names, index=1)

# ==========================================
# ROUTING & VISUALIZATION LOGIC
# ==========================================
if st.sidebar.button("Calculate Route"):
    if start_room == end_room:
        st.warning("Start and Destination are the same!")
    else:
        s_node = destinations[start_room]
        e_node = destinations[end_room]
        
        # 1. Apply Role-Based Access Control (RBAC)
        restricted_keywords = get_restrictions(selected_role)
        restricted_nodes = [
            n for n, d in graph.nodes(data=True) 
            if any(k in d.get('label', '') for k in restricted_keywords)
        ]
        
        safe_G = graph.copy()
        safe_G.remove_nodes_from(restricted_nodes)
        
        # 2. Check if route is possible
        if s_node not in safe_G or e_node not in safe_G:
            st.error(f"Access Denied: This route is restricted for your role ({selected_role}).")
        else:
            try:
                # 3. Calculate mathematical path
                path = nx.shortest_path(safe_G, s_node, e_node, weight='weight')
                
                # --- PLOTLY MAP VISUALIZATION ---
                dx_min, dx_max, dy_min, dy_max = MASTER_BOUNDS
                fig = go.Figure()
                
                # Load Background Image (Ensure PNG is in the same folder)
                img_path = "new block-UG_EXPORT.png" 
                
                try:
                    img = Image.open(img_path)
                    
                    # The "Anti-Pancake" Aspect Ratio Math (Bulletproof method)
                    img_w, img_h = img.size  
                    img_ratio = img_w / img_h
                    
                    cad_w = dx_max - dx_min
                    cad_h = dy_max - dy_min
                    true_image_height = cad_w / img_ratio
                    
                    # Calculate image anchor center
                    y_center = dy_min + (cad_h / 2.0)
                    y_adjusted_max = y_center + (true_image_height / 2.0)
                    
                    # Draw Background Image
                    fig.add_layout_image(
                        dict(
                            source=img,
                            xref="x", yref="y",
                            x=dx_min, y=y_adjusted_max,
                            sizex=cad_w,
                            sizey=true_image_height,
                            sizing="stretch", 
                            opacity=0.9,
                            layer="below"
                        )
                    )
                except FileNotFoundError:
                    st.warning(f"Could not find {img_path}. Displaying route without background.")
                    
                # 4. Extract Route Coordinates (Simple Filter)
                path_x = []
                path_y = []
                
                for p in path:
                    # Basic bounding box filter to grab local nodes
                    if (dx_min - 500) <= p[0] <= (dx_max + 500) and (dy_min - 500) <= p[1] <= (dy_max + 500):
                        path_x.append(p[0])
                        path_y.append(p[1])
                        
                # 5. Draw the Red Route Line
                if len(path_x) > 0:
                    fig.add_trace(go.Scatter(
                        x=path_x, y=path_y,
                        mode='lines',
                        line=dict(color='red', width=4),
                        name='Optimal Route'
                    ))
                    
                    # Mark Start and End Points visually
                    fig.add_trace(go.Scatter(
                        x=[path_x[0], path_x[-1]], 
                        y=[path_y[0], path_y[-1]],
                        mode='markers+text',
                        marker=dict(color=['green', 'blue'], size=12),
                        text=['Start', 'End'],
                        textposition="top center",
                        name='Locations'
                    ))
                    
                # 6. Configure Plot axes to match the bounding box
                fig.update_layout(
                    xaxis=dict(range=[dx_min, dx_max], showgrid=False, zeroline=False, visible=False),
                    yaxis=dict(range=[dy_min, dy_max], showgrid=False, zeroline=False, visible=False, scaleanchor="x", scaleratio=1),
                    margin=dict(l=0, r=0, t=0, b=0),
                    plot_bgcolor="rgba(0,0,0,0)"
                )
                
                # Render the map in Streamlit
                st.plotly_chart(fig, use_container_width=True)
                
                # Display Success
                st.success("Route generated successfully!")
                
                # ==========================================
                # ADD THE TEXT ITINERARY & OPTIONS HERE!
                # ==========================================
                st.markdown("### 📋 Step-by-Step Itinerary & Options")
                
                # Call your backend Operations Research function to get the text table
                itinerary_text = find_optimized_paths(graph, destinations, start_room, end_room, selected_role)
                
                # Print it using st.text() so it keeps your perfect column spacing!
                st.text(itinerary_text)
                
            except nx.NetworkXNoPath:
                st.error(f"No valid path found for {selected_role} between these locations.")
