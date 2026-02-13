"""Schema conformance tests to detect drift between schema.sql and hook DDL.

Ensures hooks/set_state.sh stays in sync with src/waggle/schema.sql.
"""

import re
from pathlib import Path


def test_hook_schema_matches_canonical():
    """Verify hooks/set_state.sh DDL matches src/waggle/schema.sql."""
    # Read canonical schema
    schema_path = Path(__file__).parent.parent / "src" / "waggle" / "schema.sql"
    canonical_ddl = schema_path.read_text()
    
    # Extract columns from canonical schema
    canonical_columns = extract_columns(canonical_ddl)
    
    # Read hook script
    hook_path = Path(__file__).parent.parent / "hooks" / "set_state.sh"
    hook_script = hook_path.read_text()
    
    # Extract CREATE TABLE from hook
    hook_ddl = extract_create_table(hook_script)
    hook_columns = extract_columns(hook_ddl)
    
    # Assert columns match
    assert canonical_columns == hook_columns, (
        f"Schema drift detected!\n"
        f"Canonical: {canonical_columns}\n"
        f"Hook: {hook_columns}"
    )
    
    # Extract INSERT column list from hook
    insert_columns = extract_insert_columns(hook_script)
    expected_insert = [col[0] for col in canonical_columns]
    
    # Assert INSERT columns match schema order
    assert insert_columns == expected_insert, (
        f"INSERT column mismatch!\n"
        f"Expected: {expected_insert}\n"
        f"Hook: {insert_columns}"
    )


def extract_columns(ddl: str) -> list[tuple[str, str, str]]:
    """Extract (name, type, constraints) from CREATE TABLE statement.
    
    Returns list of tuples: [(col_name, col_type, constraints), ...]
    """
    # Find column definitions between parentheses
    match = re.search(r'CREATE TABLE[^(]*\((.*?)\)', ddl, re.DOTALL | re.IGNORECASE)
    if not match:
        raise ValueError(f"No CREATE TABLE found in DDL: {ddl[:100]}")
    
    column_block = match.group(1)
    columns = []
    
    # Parse each line that looks like a column definition
    for line in column_block.split('\n'):
        line = line.strip()
        if not line or line.startswith('--'):
            continue
            
        # Remove trailing comma
        line = line.rstrip(',')
        
        # Parse: column_name TYPE [CONSTRAINTS]
        parts = line.split(None, 2)
        if len(parts) < 2:
            continue
            
        col_name = parts[0]
        col_type = parts[1]
        col_constraints = parts[2] if len(parts) > 2 else ''
        
        columns.append((col_name, col_type, col_constraints))
    
    return columns


def extract_create_table(script: str) -> str:
    """Extract CREATE TABLE statement from bash heredoc."""
    # Find the CREATE TABLE block within the heredoc
    match = re.search(
        r'CREATE TABLE IF NOT EXISTS state \((.*?)\);',
        script,
        re.DOTALL
    )
    if not match:
        raise ValueError("No CREATE TABLE found in hook script")
    
    # Reconstruct the full statement
    return f"CREATE TABLE IF NOT EXISTS state ({match.group(1)});"


def extract_insert_columns(script: str) -> list[str]:
    """Extract column list from INSERT OR REPLACE statement."""
    match = re.search(
        r'INSERT OR REPLACE INTO state \((.*?)\)',
        script
    )
    if not match:
        raise ValueError("No INSERT statement found in hook script")
    
    columns_str = match.group(1)
    # Split by comma and strip whitespace
    return [col.strip() for col in columns_str.split(',')]
