"""
Review Buddy - Streamlit GUI

A simple, clean GUI for the three-step paper review pipeline:
1. Search/Upload → 2. Filter (normal/AI) → 3. Download

Usage:
    streamlit run app.py
"""

import sys
from pathlib import Path
import tempfile
import logging

import streamlit as st
import pandas as pd

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from core.config_loader import load_config, PipelineConfig
from core.io import load_papers, save_papers, get_papers_dataframe
from core.engines import get_filter_engine
from core.postprocess import postprocess_results
from src.paper_searcher import PaperSearcher
from src.config import Config
from src.searchers.paper_downloader import PaperDownloader
from dotenv import load_dotenv


# Load environment
load_dotenv()

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# Page config
st.set_page_config(
    page_title="Review Buddy",
    page_icon="📚",
    layout="wide",
    initial_sidebar_state="expanded"
)


# Initialize session state
if 'papers' not in st.session_state:
    st.session_state.papers = None
if 'filtered_papers' not in st.session_state:
    st.session_state.filtered_papers = None
if 'filter_results' not in st.session_state:
    st.session_state.filter_results = None
if 'config' not in st.session_state:
    try:
        st.session_state.config = load_config("config.yaml")
    except:
        st.session_state.config = PipelineConfig()


def main():
    """Main app"""
    
    # Header
    st.title("📚 Review Buddy")
    st.markdown("**Intelligent Paper Search, Filtering, and Download**")
    st.markdown("---")
    
    # Sidebar - Configuration
    with st.sidebar:
        st.header("⚙️ Configuration")
        
        # Load config file
        config_file = st.file_uploader(
            "Upload config.yaml (optional)",
            type=['yaml', 'yml'],
            help="Upload a custom configuration file"
        )
        
        if config_file:
            with tempfile.NamedTemporaryFile(delete=False, suffix='.yaml') as tmp:
                tmp.write(config_file.read())
                tmp_path = tmp.name
            st.session_state.config = load_config(tmp_path)
            st.success("✓ Config loaded")
        
        st.markdown("---")
        
        # Quick settings
        st.subheader("Quick Settings")
        
        filter_engine = st.selectbox(
            "Filter Engine",
            options=["normal", "ai"],
            index=0 if st.session_state.config.engine == "normal" else 1,
            help="Choose keyword-based (normal) or AI-powered (ai) filtering"
        )
        st.session_state.config.engine = filter_engine
        
        if filter_engine == "ai":
            st.info("💡 AI filtering requires Ollama running locally")
            ai_model = st.text_input(
                "Ollama Model",
                value=st.session_state.config.ai.model,
                help="e.g., llama3.1:8b"
            )
            st.session_state.config.ai.model = ai_model
        
        st.markdown("---")
        
        # Info
        st.markdown("""
        ### 📖 How to Use
        
        1. **Search/Upload**: Search databases or upload existing papers
        2. **Filter**: Apply keyword or AI filters  
        3. **Download**: Get PDFs with smart fallback
        
        ### 🔗 Links
        - [Documentation](https://github.com/yourusername/review_buddy)
        - [Report Issue](https://github.com/yourusername/review_buddy/issues)
        """)
    
    # Main content - Three steps
    tab1, tab2, tab3 = st.tabs(["🔍 Step 1: Search", "🎯 Step 2: Filter", "⬇️ Step 3: Download"])
    
    # ===== TAB 1: SEARCH / UPLOAD =====
    with tab1:
        st.header("🔍 Search or Upload Papers")
        
        mode = st.radio(
            "Choose mode:",
            options=["Search databases", "Upload existing file"],
            horizontal=True
        )
        
        if mode == "Search databases":
            search_mode()
        else:
            upload_mode()
    
    # ===== TAB 2: FILTER =====
    with tab2:
        st.header("🎯 Filter Papers")
        
        if st.session_state.papers is None:
            st.warning("⚠️ Please complete Step 1 first (Search or Upload papers)")
        else:
            filter_mode()
    
    # ===== TAB 3: DOWNLOAD =====
    with tab3:
        st.header("⬇️ Download PDFs")
        
        if st.session_state.filtered_papers is None:
            st.warning("⚠️ Please complete Step 2 first (Filter papers)")
        else:
            download_mode()


def search_mode():
    """Search mode UI"""
    st.subheader("Configure Search")
    
    col1, col2 = st.columns(2)
    
    with col1:
        query = st.text_area(
            "Search Query",
            value=st.session_state.config.search.query,
            height=100,
            help="Use Boolean operators: AND, OR, NOT, quotes for phrases"
        )
    
    with col2:
        year_from = st.number_input(
            "Year From",
            min_value=1900,
            max_value=2030,
            value=st.session_state.config.search.year_from,
            help="Filter papers from this year onwards"
        )
        
        max_results = st.number_input(
            "Max Results Per Source",
            min_value=1,
            max_value=10000,
            value=min(st.session_state.config.search.max_results_per_source, 100),
            help="Limit results per database (default: 100 for GUI)"
        )
    
    if st.button("🔍 Search", type="primary", use_container_width=True):
        if not query.strip():
            st.error("Please enter a search query")
            return
        
        with st.spinner("Searching databases..."):
            try:
                # Create searcher
                config = Config(max_results_per_source=max_results)
                searcher = PaperSearcher(config)
                
                # Search
                papers = searcher.search_all(query=query, year_from=year_from)
                
                if not papers:
                    st.warning("No papers found. Try a different query or check API keys in .env")
                    return
                
                # Store in session
                st.session_state.papers = papers
                st.session_state.filtered_papers = None  # Reset filtered
                
                # Success message
                st.success(f"✅ Found {len(papers)} unique papers!")
                
                # Show preview
                show_papers_preview(papers, "Search Results")
                
            except Exception as e:
                st.error(f"Search failed: {e}")
                logger.exception("Search error")


def upload_mode():
    """Upload existing file mode"""
    st.subheader("Upload Existing Papers")
    
    uploaded_file = st.file_uploader(
        "Choose a file",
        type=['bib', 'bibtex', 'csv'],
        help="Upload BibTeX or CSV file with papers"
    )
    
    if uploaded_file:
        with st.spinner("Loading papers..."):
            try:
                # Save to temp file
                with tempfile.NamedTemporaryFile(delete=False, suffix=Path(uploaded_file.name).suffix) as tmp:
                    tmp.write(uploaded_file.read())
                    tmp_path = tmp.name
                
                # Load papers
                papers = load_papers(tmp_path)
                
                if not papers:
                    st.warning("No papers found in file")
                    return
                
                # Store in session
                st.session_state.papers = papers
                st.session_state.filtered_papers = None  # Reset filtered
                
                st.success(f"✅ Loaded {len(papers)} papers!")
                
                # Show preview
                show_papers_preview(papers, "Uploaded Papers")
                
            except Exception as e:
                st.error(f"Failed to load file: {e}")
                logger.exception("Upload error")


def filter_mode():
    """Filter mode UI"""
    papers = st.session_state.papers
    config = st.session_state.config
    
    st.info(f"📊 Loaded: **{len(papers)} papers** | Engine: **{config.engine}**")
    
    # Show current papers
    with st.expander("📋 View Papers to Filter", expanded=False):
        show_papers_preview(papers, "Papers to Filter", max_rows=100)
    
    st.markdown("---")
    
    # Filter settings
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.subheader(f"Configure {config.engine.upper()} Filter")
    
    with col2:
        if st.button("🎯 Apply Filters", type="primary", use_container_width=True):
            apply_filters()
    
    # Engine-specific settings
    if config.engine == "normal":
        show_normal_filter_settings()
    else:
        show_ai_filter_settings()
    
    # Show filtered results if available
    if st.session_state.filter_results:
        st.markdown("---")
        show_filter_results()


def show_normal_filter_settings():
    """Show normal filter configuration"""
    config = st.session_state.config
    
    st.markdown("**Select filters to apply:**")
    
    available_filters = ["no_abstract", "non_english", "non_human", "non_empirical"]
    available_filters.extend(list(config.normal.keywords.keys()))
    
    selected = st.multiselect(
        "Enabled Filters",
        options=available_filters,
        default=config.normal.enabled_filters,
        help="Choose which filters to apply"
    )
    
    config.normal.enabled_filters = selected
    
    # Show keyword counts
    if config.normal.keywords:
        st.markdown("**Custom keyword filters:**")
        for name, keywords in config.normal.keywords.items():
            st.text(f"  • {name}: {len(keywords)} keywords")


def show_ai_filter_settings():
    """Show AI filter configuration"""
    config = st.session_state.config
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.text(f"Model: {config.ai.model}")
        st.text(f"Ollama URL: {config.ai.ollama_url}")
    
    with col2:
        confidence = st.slider(
            "Confidence Threshold",
            min_value=0.0,
            max_value=1.0,
            value=config.ai.confidence_threshold,
            step=0.1,
            help="Minimum confidence to filter (higher = more conservative)"
        )
        config.ai.confidence_threshold = confidence
    
    # Show enabled filters
    enabled = [name for name, cfg in config.ai.filters.items() if cfg.get('enabled', True)]
    st.markdown(f"**Enabled AI filters:** {', '.join(enabled)}")


def apply_filters():
    """Apply filters and show results"""
    papers = st.session_state.papers
    config = st.session_state.config
    
    with st.spinner(f"Applying {config.engine} filters..."):
        try:
            # Get filter engine
            filter_config = config.get_filter_config()
            engine = get_filter_engine(config.engine, filter_config)
            
            # Filter
            results = engine.filter_records(papers)
            
            # Store results
            st.session_state.filter_results = results
            st.session_state.filtered_papers = results['kept']
            
            st.success(f"✅ Filtering complete! Kept {len(results['kept'])}/{len(papers)} papers")
            
        except Exception as e:
            st.error(f"Filtering failed: {e}")
            logger.exception("Filter error")


def show_filter_results():
    """Display filtering results"""
    results = st.session_state.filter_results
    summary = results['summary']
    
    st.subheader("📊 Filtering Summary")
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("Initial Papers", summary['initial_count'])
    with col2:
        st.metric("Papers Kept", summary['final_count'])
    with col3:
        st.metric("Filtered Out", summary['total_filtered'])
    with col4:
        retention = summary['final_count'] / summary['initial_count'] * 100 if summary['initial_count'] > 0 else 0
        st.metric("Retention Rate", f"{retention:.1f}%")
    
    # Breakdown by filter
    st.markdown("**Breakdown by filter:**")
    filter_df = pd.DataFrame([
        {"Filter": name, "Papers Filtered": count}
        for name, count in summary['filtered_by_category'].items()
    ])
    st.dataframe(filter_df, use_container_width=True, hide_index=True)
    
    # Show kept papers
    with st.expander("📋 View Kept Papers", expanded=False):
        show_papers_preview(results['kept'], "Kept Papers", max_rows=100)
    
    # Show manual review if AI
    if 'manual_review' in results and results['manual_review']:
        st.warning(f"⚠️ {len(results['manual_review'])} papers flagged for manual review")
        with st.expander("📋 View Papers for Manual Review"):
            show_papers_preview(results['manual_review'], "Manual Review", max_rows=100)


def download_mode():
    """Download mode UI"""
    papers = st.session_state.filtered_papers
    config = st.session_state.config
    
    st.info(f"📊 Ready to download: **{len(papers)} papers**")
    
    # Download settings
    col1, col2 = st.columns(2)
    
    with col1:
        output_dir = st.text_input(
            "Output Directory",
            value=config.io.pdf_dir,
            help="Directory to save PDFs"
        )
    
    with col2:
        use_scihub = st.checkbox(
            "Enable Sci-Hub fallback",
            value=config.download.use_scihub,
            help="Use Sci-Hub as last resort (check local laws)"
        )
    
    email = st.text_input(
        "Unpaywall Email (optional)",
        value=config.download.unpaywall_email or "",
        help="Email for Unpaywall API (improves success rate)"
    )
    
    if st.button("⬇️ Download PDFs", type="primary", use_container_width=True):
        with st.spinner("Downloading PDFs..."):
            try:
                # Save papers to temp bib file
                with tempfile.NamedTemporaryFile(delete=False, suffix='.bib', mode='w') as tmp:
                    from src.utils import save_papers_bib
                    save_papers_bib(papers, Path(tmp.name))
                    bib_path = tmp.name
                
                # Create output dir
                Path(output_dir).mkdir(parents=True, exist_ok=True)
                
                # Download
                downloader = PaperDownloader(
                    output_dir=output_dir,
                    use_scihub=use_scihub,
                    unpaywall_email=email if email else None
                )
                
                # Use progress bar
                progress_bar = st.progress(0)
                status_text = st.empty()
                
                downloader.download_from_bib(bib_path)
                
                progress_bar.progress(100)
                
                # Count results
                pdf_count = len([f for f in Path(output_dir).iterdir() if f.suffix == ".pdf"])
                
                st.success(f"✅ Downloaded {pdf_count} PDFs to {output_dir}")
                
                # Show download log excerpt
                log_file = Path(output_dir) / "download.log"
                if log_file.exists():
                    with st.expander("📄 View Download Log (last 50 lines)"):
                        with open(log_file, 'r') as f:
                            lines = f.readlines()
                            st.text("".join(lines[-50:]))
                
            except Exception as e:
                st.error(f"Download failed: {e}")
                logger.exception("Download error")


def show_papers_preview(papers, title, max_rows=20):
    """Show papers in a table"""
    st.subheader(title)
    
    df = get_papers_dataframe(papers)
    
    # Show only first max_rows
    if len(df) > max_rows:
        st.dataframe(df.head(max_rows), use_container_width=True, hide_index=True)
        st.info(f"Showing first {max_rows} of {len(df)} papers")
    else:
        st.dataframe(df, use_container_width=True, hide_index=True)
    
    # Download buttons
    col1, col2 = st.columns(2)
    
    with col1:
        csv_data = df.to_csv(index=False).encode('utf-8')
        st.download_button(
            label="📥 Download CSV",
            data=csv_data,
            file_name=f"{title.lower().replace(' ', '_')}.csv",
            mime="text/csv",
            use_container_width=True
        )
    
    with col2:
        # Generate BibTeX
        with tempfile.NamedTemporaryFile(delete=False, suffix='.bib', mode='w') as tmp:
            from src.utils import save_papers_bib
            save_papers_bib(papers, Path(tmp.name))
            with open(tmp.name, 'r') as f:
                bib_data = f.read().encode('utf-8')
        
        st.download_button(
            label="📥 Download BibTeX",
            data=bib_data,
            file_name=f"{title.lower().replace(' ', '_')}.bib",
            mime="text/plain",
            use_container_width=True
        )


if __name__ == "__main__":
    main()
