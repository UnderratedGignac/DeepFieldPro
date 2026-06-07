import os
import ast

def get_docstring_or_preview(filepath):
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Try to parse and get docstring
        tree = ast.parse(content)
        docstring = ast.get_docstring(tree)
        if docstring:
            return docstring.strip()
        
        # Fallback: return first 5 lines of code
        lines = [line.strip() for line in content.split('\n') if line.strip() and not line.startswith('import ') and not line.startswith('from ')]
        if not lines:
            return "Empty or import-only file."
        return "\n".join(lines[:5]) + "\n..."
    except Exception as e:
        return f"Could not parse file: {str(e)}"

def generate_docs():
    output = []
    output.append("# 📖 DeepFieldPro: Comprehensive Master Documentation\n")
    output.append("## 🏗 Architectural Rationale: \"Why I did it like this\"\n")
    output.append("The DeepFieldPro system was originally designed with an extremely complex tech stack (PostgreSQL, TimescaleDB, Redis, Microservices). However, to make the system **highly robust, hyper-fast, and run smoothly on a local machine without Docker overhead**, the architecture was fundamentally refactored. Here is why the core decisions were made:\n")
    output.append("1. **SQLite3 over PostgreSQL:** We shifted to local SQLite databases (`bankroll.db`, `bet_log.db`, `odds_stream.db`). Why? Because for a single-node AI betting engine, network latency and database connection pooling to a heavy Postgres instance create unnecessary friction. SQLite provides lightning-fast reads/writes with zero setup required.\n")
    output.append("2. **Flat-File JSON State for UI (`todays_dashboard_state.json`):** Instead of hitting the database for every UI render, the background daemon periodically exports its entire mental model to a single JSON file. The Flask UI Server (`live_dashboard_server.py`) simply serves this file. Why? This completely decouples the heavy AI inference loop from the web server, ensuring the UI remains blazing fast and never causes database lock contention.\n")
    output.append("3. **Strict Lineup Validation (`has_lineup` rule):** The engine refuses to execute predictions on matches without confirmed starting XIs. Why? Because pre-match estimated lineups introduce massive variance. A key player getting benched destroys the statistical edge. By enforcing strict lineup checks, the AI only bets when it has absolute certainty of the field conditions.\n")
    output.append("4. **Kelly Criterion Fractional Sizing:** We integrated a strict bankroll tracker that sizes bets based on the mathematical edge (EV). Why? To mathematically guarantee long-term capital preservation and maximize compounding growth while strictly capping daily exposure to prevent catastrophic ruin.\n")
    output.append("5. **Expanded Prop Markets (Corners, Shots, Goalscorers):** While 1X2 and Over/Under are highly efficient markets (hard to beat), prop markets often have softer pricing due to bookmaker generalization. The AI specifically hunts for alphas in these secondary markets.\n")
    
    output.append("\n## 📂 File-by-File Codebase Audit\n")
    
    src_dir = "src"
    
    # Walk through all files
    all_files = []
    for root, dirs, files in os.walk(src_dir):
        # exclude __pycache__
        dirs[:] = [d for d in dirs if d not in ['__pycache__', 'scratch', '.pytest_cache']]
        for file in files:
            if file.endswith('.py') and file != '__init__.py':
                all_files.append(os.path.join(root, file))
                
    # Group by directory
    grouped = {}
    for filepath in all_files:
        dir_name = os.path.dirname(filepath)
        if dir_name not in grouped:
            grouped[dir_name] = []
        grouped[dir_name].append(filepath)
        
    for dir_name in sorted(grouped.keys()):
        output.append(f"### 📁 Directory: `{dir_name}`\n")
        for filepath in sorted(grouped[dir_name]):
            filename = os.path.basename(filepath)
            docstring = get_docstring_or_preview(filepath)
            
            output.append(f"#### 📄 `{filename}`")
            output.append("```python\n" + docstring + "\n```\n")
            
    with open("DEEPFIELD_DOCUMENTATION.md", "w", encoding="utf-8") as f:
        f.write("\n".join(output))

if __name__ == "__main__":
    generate_docs()
    print("Documentation generated successfully.")
