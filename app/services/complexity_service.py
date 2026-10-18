import re
import hashlib
import os
from typing import Dict, Tuple

def compute_code_hash(code: str) -> str:
    """Returns SHA256 hash of normalized code to detect modifications."""
    normalized = "".join(code.split())
    return hashlib.sha256(normalized.encode('utf-8')).hexdigest()

def analyze_complexity(code: str, language: str = "python") -> Dict[str, str]:
    """
    Analyzes code to estimate Time and Auxiliary Space complexity with explanatory details.
    Uses static pattern and structure analysis across Python, C++, Java, and JavaScript.
    Returns:
        {
            "time_complexity": "O(...)",
            "space_complexity": "O(...)",
            "explanation": "...",
            "status": "Completed" | "Unable to Analyze",
            "code_hash": "..."
        }
    """
    stripped_code = code.strip()
    code_hash = compute_code_hash(stripped_code)

    # 1. Handle empty or stub code
    if not stripped_code or len(stripped_code) < 15 or "pass" == stripped_code:
        return {
            "time_complexity": "Unable to determine",
            "space_complexity": "Unable to determine",
            "explanation": "Unable to determine confidently: code is empty or a placeholder stub.",
            "status": "Unable to Analyze",
            "code_hash": code_hash
        }

    # Normalize comments out for analysis
    clean_lines = []
    for line in stripped_code.splitlines():
        trimmed = line.strip()
        if trimmed.startswith("#") or trimmed.startswith("//"):
            continue
        clean_lines.append(line)
    clean_code = "\n".join(clean_lines)

    if not clean_code.strip():
        return {
            "time_complexity": "Unable to determine",
            "space_complexity": "Unable to determine",
            "explanation": "Unable to determine confidently: only comments detected.",
            "status": "Unable to Analyze",
            "code_hash": code_hash
        }

    # 2. Check for Sorting algorithms
    has_sort = bool(re.search(
        r'(\.sort\(|sorted\(|std::sort|Arrays\.sort|Collections\.sort|\.sort\s*\()',
        clean_code
    ))

    # 3. Check for Binary Search patterns
    has_binary_search = bool(
        re.search(r'(mid\s*=\s*\(?[a-zA-Z0-9_]+\s*\+\s*[a-zA-Z0-9_]+\)?\s*(//|/|>>)\s*2|\b(lower_bound|upper_bound|binary_search)\b)', clean_code)
        and re.search(r'\b(left|low|l)\s*<=?\s*(right|high|r)\b', clean_code)
    )

    # 4. Check for Recursion (including nested helper functions like dfs, helper, solve)
    defined_funcs = set(re.findall(r'(?:def|void|int|bool|function|public\s+\w+|const|let|auto)\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*\(', clean_code))
    # Also include common recursive idioms
    for idiom in ["dfs", "backtrack", "helper", "solve", "recurse", "partition"]:
        if re.search(rf'\b{idiom}\s*\(', clean_code):
            defined_funcs.add(idiom)

    recursive_calls_count = 0
    ignored_names = {"for", "while", "if", "print", "len", "range", "main", "swap", "min", "max", "sum"}
    for fn in defined_funcs:
        if fn in ignored_names:
            continue
        call_matches = re.findall(rf'\b{re.escape(fn)}\s*\(', clean_code)
        # If function is called 2 or more times (or >= 1 if idiom called within body)
        if len(call_matches) >= 2:
            recursive_calls_count = max(recursive_calls_count, len(call_matches) - 1)

    has_memoization = bool(re.search(r'(@lru_cache|@cache|memo|dp\[|seen\b|memoization)', clean_code, re.IGNORECASE))

    # 5. Check Loop Nesting Depth
    # Compute maximum nested loop depth using indentation or block structure
    max_loop_depth = 0
    current_loop_depth = 0

    lines = clean_code.splitlines()
    for line in lines:
        trimmed = line.strip()
        is_loop = bool(re.match(r'^(for|while)\b', trimmed) or re.search(r'\b(for|while)\s*\(', trimmed))
        if is_loop:
            current_loop_depth += 1
            if current_loop_depth > max_loop_depth:
                max_loop_depth = current_loop_depth
        elif "}" in trimmed or (language == "python" and len(line) - len(line.lstrip()) == 0 and trimmed):
            current_loop_depth = max(0, current_loop_depth - 1)

    # Re-verify nested loop with regex pattern
    has_three_loops = bool(re.search(r'for[^{:\n]+[{:\n][^}]*?for[^{:\n]+[{:\n][^}]*?for', clean_code, re.DOTALL))
    has_two_loops = bool(re.search(r'for[^{:\n]+[{:\n][^}]*?for', clean_code, re.DOTALL) or re.search(r'while[^{:\n]+[{:\n][^}]*?while', clean_code, re.DOTALL))
    has_single_loop = bool(re.search(r'\b(for|while)\b', clean_code))

    if has_three_loops:
        loop_depth = 3
    elif has_two_loops:
        loop_depth = 2
    elif has_single_loop:
        loop_depth = 1
    else:
        loop_depth = 0

    # 6. Check for logarithmic stepping inside while/for (e.g. n //= 2 or i *= 2)
    has_log_stride = bool(re.search(r'(\*=\s*2|/=\s*2|//=\s*2|>>=\s*1)', clean_code))

    # 7. Check Data Structures for Auxiliary Space
    uses_2d_table = bool(re.search(r'(\[\[[^\]]+\]\s*for\s+|_matrix|vector<vector<|int\[\]\[\]|Array\.from)', clean_code))
    uses_hash_structure = bool(re.search(r'(dict\(|\{\}|unordered_map|HashMap|HashSet|new\s+Map|new\s+Set|\bset\(|\bdefaultdict\b)', clean_code))
    uses_heap = bool(re.search(r'(heapq|priority_queue|PriorityQueue)', clean_code))
    uses_list_allocation = bool(re.search(r'(\.append\(|\.push_back\(|\.push\(|\.add\(|new\s+ArrayList)', clean_code))

    # --- TIME COMPLEXITY DETERMINATION ---
    time_comp = "O(1)"
    time_reason = ""

    if recursive_calls_count >= 2:
        if has_memoization:
            time_comp = "O(n)"
            time_reason = f"Recursive approach with memoization/caching: avoids redundant subproblems, scaling linearly with state space O(n)."
        else:
            time_comp = "O(2^n)"
            time_reason = f"Multiple branching recursive calls ({recursive_calls_count} calls per step) without memoization: creates an exponential call tree O(2^n)."
    elif recursive_calls_count == 1:
        if has_binary_search or has_log_stride:
            time_comp = "O(log n)"
            time_reason = "Single recursive call dividing the problem size in half each step: logarithmic O(log n) time."
        elif has_single_loop:
            time_comp = "O(n log n)" if has_sort else "O(n)"
            time_reason = "Linear recursive traversal combined with loop: O(n) time."
        else:
            time_comp = "O(n)"
            time_reason = "Linear recursion processing one element per stack frame: O(n) time."
    elif loop_depth >= 3:
        time_comp = "O(n³)"
        time_reason = f"Detected {loop_depth} levels of nested loops iterating across input elements: cubic O(n³) time."
    elif loop_depth == 2:
        if has_log_stride:
            time_comp = "O(n log n)"
            time_reason = "Outer loop iterating n times with inner logarithmic step progression: O(n log n) time."
        else:
            time_comp = "O(n²)"
            time_reason = "Two nested loops iterating over input elements: quadratic O(n²) time."
    elif has_sort:
        if loop_depth == 1:
            time_comp = "O(n log n)"
            time_reason = "Sorting step dominates with O(n log n) time followed by a linear pass O(n)."
        else:
            time_comp = "O(n log n)"
            time_reason = "Standard comparison-based sorting: O(n log n) time."
    elif has_binary_search or has_log_stride:
        time_comp = "O(log n)"
        time_reason = "Binary search / divide-and-conquer halving the search space each iteration: O(log n) time."
    elif loop_depth == 1:
        # Two-pointer or linear pass
        if bool(re.search(r'\b(left|l)\s*<\s*(right|r)\b', clean_code)):
            time_comp = "O(n)"
            time_reason = "Two-pointer linear convergence: each element is visited at most once O(n)."
        else:
            time_comp = "O(n)"
            time_reason = "Single loop scanning through n elements: linear O(n) time."
    else:
        # Check if constant math / expressions
        if len(clean_code.splitlines()) <= 8 and not has_single_loop:
            time_comp = "O(1)"
            time_reason = "Direct mathematical computation or variable lookup: constant O(1) time."
        else:
            time_comp = "O(1)"
            time_reason = "No loops or recursion detected: executes in constant O(1) time."

    # --- SPACE COMPLEXITY DETERMINATION ---
    space_comp = "O(1)"
    space_reason = ""

    if uses_2d_table:
        space_comp = "O(n²)"
        space_reason = "Allocates a 2D matrix / table for dynamic programming or grid storage: O(n²) auxiliary space."
    elif uses_hash_structure or uses_list_allocation:
        if recursive_calls_count > 0:
            space_comp = "O(n)"
            space_reason = "Uses dynamic auxiliary data structures (hash map / list) plus call stack depth proportional to n: O(n) space."
        else:
            space_comp = "O(n)"
            space_reason = "Auxiliary hash table or dynamic list storing elements proportional to input size: O(n) space."
    elif uses_heap:
        space_comp = "O(k)"
        space_reason = "Maintains a priority queue / heap of size k: O(k) auxiliary space."
    elif recursive_calls_count > 0:
        if has_binary_search or has_log_stride:
            space_comp = "O(log n)"
            space_reason = "Recursive call stack depth scales logarithmically with problem size: O(log n) auxiliary space."
        else:
            space_comp = "O(n)"
            space_reason = "Recursive call stack depth reaches up to n frames: O(n) auxiliary space."
    else:
        space_comp = "O(1)"
        space_reason = "Modifies variables in-place without allocating auxiliary collections: constant O(1) space."

    full_explanation = f"{time_reason} {space_reason}"

    return {
        "time_complexity": time_comp,
        "space_complexity": space_comp,
        "explanation": full_explanation.strip(),
        "status": "Completed",
        "code_hash": code_hash
    }
