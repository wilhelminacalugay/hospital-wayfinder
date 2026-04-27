import streamlit as st
import matplotlib.pyplot as plt
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

# Load the data
with st.spinner("Loading structural network geometry..."):
    net, db = load_hospital_data()

# ==========================================
# THE INTERACTIVE USER INTERFACE
# ==========================================
if net and db:
    all_rooms = sorted(list(db.keys()))
    
    # 1. SIDEBAR CONTROLS (Professional Layout)
    with st.sidebar:
        st.header("Navigation Parameters")
        
        role_options = ["DOCTOR", "STAFF", "PATIENT", "VISITOR", "PWD"]
        user_role = st.selectbox("👤 Security Clearance:", options=role_options, index=3)
        
        st.divider()
        
        start_point = st.selectbox("📍 Current Location:", options=all_rooms, index=all_rooms.index("MAIN ROAD") if "MAIN ROAD" in all_rooms else 0)
        destination = st.selectbox("🏁 Destination:", options=all_rooms, index=all_rooms.index("PANTRY 4F") if "PANTRY 4F" in all_rooms else 1)
        
        st.divider()
        calculate_btn = st.button("Calculate Optimal Route", type="primary", use_container_width=True)

    # 2. MAIN DASHBOARD DISPLAY
    if calculate_btn:
        if start_point == destination:
            st.warning("You are already at your destination!")
        else:
            with st.spinner("Calculating multi-objective trade-offs..."):
                # Run the backend operations research engine
                result = find_optimized_paths(net, db, start_point, destination, user_role)
                
                # KPI METRIC SCORECARDS
                col1, col2, col3 = st.columns(3)
                col1.metric("Nodes Evaluated", len(net.nodes))
                col2.metric("Corridors Scanned", len(net.edges))
                col3.metric("Active Clearance", user_role)
                
                st.divider()
                
                # LAYOUT SPLIT: Text Results on left, Map on right
                text_col, map_col = st.columns([1, 1.2])
                
                with text_col:
                    st.markdown("### Recommended Itineraries")
                    st.success("Routing Complete.")
                    st.code(result, language="markdown")
                    
                    # 3. DOWNLOADABLE ITINERARY
                    st.download_button(
                        label="📥 Download Route Instructions",
                        data=result,
                        file_name=f"Hospital_Route_{start_point}_to_{destination}.txt",
                        mime="text/plain",
                        use_container_width=True
                    )
                
                with map_col:
                    st.markdown("### Structural Spatial Map")
                    
                    # 4. ARCHITECTURAL VISUALIZATION
                    fig, ax = plt.subplots(figsize=(8, 6))
                    fig.patch.set_facecolor('#0E1117') # Match Streamlit dark mode
                    ax.set_facecolor('#0E1117')
                    
                    # Extract the literal X,Y coordinates from your DXF nodes
                    pos = {node: node for node in net.nodes()}
                    
                    # Draw the base hospital network in faint blue
                    nx.draw(net, pos, ax=ax, node_size=5, node_color="#4A90E2", edge_color="#333333", alpha=0.5)
                    
                    # Highlight the exact Start and End points
                    start_coords = db[start_point]
                    dest_coords = db[destination]
                    
                    nx.draw_networkx_nodes(net, pos, nodelist=[start_coords], ax=ax, node_color="#00FF00", node_size=150, label="Start")
                    nx.draw_networkx_nodes(net, pos, nodelist=[dest_coords], ax=ax, node_color="#FF0000", node_size=150, label="Destination")
                    
                    # Clean up the chart axes
                    ax.legend(facecolor='#262730', edgecolor='none', labelcolor='white')
                    ax.set_axis_off()
                    
                    st.pyplot(fig)
                    
else:
    st.error("System Offline: Could not load the hospital map data. Please check your .dxf file.")
