"""Curated starter curricula. Problems are imported without network calls;
statements are fetched lazily via /leetcode/refresh when a question is opened.

Each problem is (frontend_id, slug, title, difficulty). All entries were verified
against LeetCode's public GraphQL API, and paid-only problems are excluded.
"""
from typing import Any, Dict, List, Optional, Tuple

from fastapi import HTTPException
from pymongo.database import Database

from app.services.repo import new_folder_doc, new_question_doc, next_position

Problem = Tuple[str, str, str, str]


def _url(slug: str) -> str:
    return f"https://leetcode.com/problems/{slug}/"


CURRICULA: List[Dict[str, Any]] = [
    {
        "id": "core-interview-patterns",
        "name": "Core Interview Patterns",
        "description": "A pattern-by-pattern path through the problems that come up most in coding interviews, "
                       "from hashing warm-ups to graphs and dynamic programming.",
        "patterns": [
            ("Arrays & Hashing", [
                ("1", "two-sum", "Two Sum", "Easy"),
                ("217", "contains-duplicate", "Contains Duplicate", "Easy"),
                ("242", "valid-anagram", "Valid Anagram", "Easy"),
                ("49", "group-anagrams", "Group Anagrams", "Medium"),
                ("347", "top-k-frequent-elements", "Top K Frequent Elements", "Medium"),
                ("238", "product-of-array-except-self", "Product of Array Except Self", "Medium"),
                ("36", "valid-sudoku", "Valid Sudoku", "Medium"),
                ("128", "longest-consecutive-sequence", "Longest Consecutive Sequence", "Medium"),
                ("560", "subarray-sum-equals-k", "Subarray Sum Equals K", "Medium"),
            ]),
            ("Two Pointers", [
                ("125", "valid-palindrome", "Valid Palindrome", "Easy"),
                ("167", "two-sum-ii-input-array-is-sorted", "Two Sum II - Input Array Is Sorted", "Medium"),
                ("15", "3sum", "3Sum", "Medium"),
                ("11", "container-with-most-water", "Container With Most Water", "Medium"),
                ("42", "trapping-rain-water", "Trapping Rain Water", "Hard"),
            ]),
            ("Sliding Window", [
                ("121", "best-time-to-buy-and-sell-stock", "Best Time to Buy and Sell Stock", "Easy"),
                ("3", "longest-substring-without-repeating-characters", "Longest Substring Without Repeating Characters", "Medium"),
                ("424", "longest-repeating-character-replacement", "Longest Repeating Character Replacement", "Medium"),
                ("567", "permutation-in-string", "Permutation in String", "Medium"),
                ("76", "minimum-window-substring", "Minimum Window Substring", "Hard"),
                ("239", "sliding-window-maximum", "Sliding Window Maximum", "Hard"),
            ]),
            ("Stack", [
                ("20", "valid-parentheses", "Valid Parentheses", "Easy"),
                ("155", "min-stack", "Min Stack", "Medium"),
                ("150", "evaluate-reverse-polish-notation", "Evaluate Reverse Polish Notation", "Medium"),
                ("739", "daily-temperatures", "Daily Temperatures", "Medium"),
                ("84", "largest-rectangle-in-histogram", "Largest Rectangle in Histogram", "Hard"),
            ]),
            ("Binary Search", [
                ("704", "binary-search", "Binary Search", "Easy"),
                ("74", "search-a-2d-matrix", "Search a 2D Matrix", "Medium"),
                ("875", "koko-eating-bananas", "Koko Eating Bananas", "Medium"),
                ("153", "find-minimum-in-rotated-sorted-array", "Find Minimum in Rotated Sorted Array", "Medium"),
                ("33", "search-in-rotated-sorted-array", "Search in Rotated Sorted Array", "Medium"),
                ("981", "time-based-key-value-store", "Time Based Key-Value Store", "Medium"),
                ("4", "median-of-two-sorted-arrays", "Median of Two Sorted Arrays", "Hard"),
            ]),
            ("Linked List", [
                ("206", "reverse-linked-list", "Reverse Linked List", "Easy"),
                ("21", "merge-two-sorted-lists", "Merge Two Sorted Lists", "Easy"),
                ("141", "linked-list-cycle", "Linked List Cycle", "Easy"),
                ("143", "reorder-list", "Reorder List", "Medium"),
                ("19", "remove-nth-node-from-end-of-list", "Remove Nth Node From End of List", "Medium"),
                ("138", "copy-list-with-random-pointer", "Copy List with Random Pointer", "Medium"),
                ("146", "lru-cache", "LRU Cache", "Medium"),
                ("23", "merge-k-sorted-lists", "Merge k Sorted Lists", "Hard"),
            ]),
            ("Trees", [
                ("226", "invert-binary-tree", "Invert Binary Tree", "Easy"),
                ("104", "maximum-depth-of-binary-tree", "Maximum Depth of Binary Tree", "Easy"),
                ("543", "diameter-of-binary-tree", "Diameter of Binary Tree", "Easy"),
                ("100", "same-tree", "Same Tree", "Easy"),
                ("572", "subtree-of-another-tree", "Subtree of Another Tree", "Easy"),
                ("235", "lowest-common-ancestor-of-a-binary-search-tree", "Lowest Common Ancestor of a Binary Search Tree", "Medium"),
                ("102", "binary-tree-level-order-traversal", "Binary Tree Level Order Traversal", "Medium"),
                ("199", "binary-tree-right-side-view", "Binary Tree Right Side View", "Medium"),
                ("98", "validate-binary-search-tree", "Validate Binary Search Tree", "Medium"),
                ("230", "kth-smallest-element-in-a-bst", "Kth Smallest Element in a BST", "Medium"),
                ("105", "construct-binary-tree-from-preorder-and-inorder-traversal", "Construct Binary Tree from Preorder and Inorder Traversal", "Medium"),
                ("124", "binary-tree-maximum-path-sum", "Binary Tree Maximum Path Sum", "Hard"),
                ("297", "serialize-and-deserialize-binary-tree", "Serialize and Deserialize Binary Tree", "Hard"),
            ]),
            ("Tries", [
                ("208", "implement-trie-prefix-tree", "Implement Trie (Prefix Tree)", "Medium"),
                ("211", "design-add-and-search-words-data-structure", "Design Add and Search Words Data Structure", "Medium"),
                ("212", "word-search-ii", "Word Search II", "Hard"),
            ]),
            ("Heap / Priority Queue", [
                ("703", "kth-largest-element-in-a-stream", "Kth Largest Element in a Stream", "Easy"),
                ("1046", "last-stone-weight", "Last Stone Weight", "Easy"),
                ("973", "k-closest-points-to-origin", "K Closest Points to Origin", "Medium"),
                ("215", "kth-largest-element-in-an-array", "Kth Largest Element in an Array", "Medium"),
                ("621", "task-scheduler", "Task Scheduler", "Medium"),
                ("295", "find-median-from-data-stream", "Find Median from Data Stream", "Hard"),
            ]),
            ("Backtracking", [
                ("78", "subsets", "Subsets", "Medium"),
                ("39", "combination-sum", "Combination Sum", "Medium"),
                ("46", "permutations", "Permutations", "Medium"),
                ("79", "word-search", "Word Search", "Medium"),
                ("131", "palindrome-partitioning", "Palindrome Partitioning", "Medium"),
                ("17", "letter-combinations-of-a-phone-number", "Letter Combinations of a Phone Number", "Medium"),
                ("51", "n-queens", "N-Queens", "Hard"),
            ]),
            ("Graphs", [
                ("200", "number-of-islands", "Number of Islands", "Medium"),
                ("133", "clone-graph", "Clone Graph", "Medium"),
                ("695", "max-area-of-island", "Max Area of Island", "Medium"),
                ("417", "pacific-atlantic-water-flow", "Pacific Atlantic Water Flow", "Medium"),
                ("994", "rotting-oranges", "Rotting Oranges", "Medium"),
                ("207", "course-schedule", "Course Schedule", "Medium"),
                ("210", "course-schedule-ii", "Course Schedule II", "Medium"),
                ("684", "redundant-connection", "Redundant Connection", "Medium"),
                ("127", "word-ladder", "Word Ladder", "Hard"),
            ]),
            ("Advanced Graphs", [
                ("743", "network-delay-time", "Network Delay Time", "Medium"),
                ("1584", "min-cost-to-connect-all-points", "Min Cost to Connect All Points", "Medium"),
                ("787", "cheapest-flights-within-k-stops", "Cheapest Flights Within K Stops", "Medium"),
                ("332", "reconstruct-itinerary", "Reconstruct Itinerary", "Hard"),
                ("778", "swim-in-rising-water", "Swim in Rising Water", "Hard"),
            ]),
            ("1-D Dynamic Programming", [
                ("70", "climbing-stairs", "Climbing Stairs", "Easy"),
                ("746", "min-cost-climbing-stairs", "Min Cost Climbing Stairs", "Easy"),
                ("198", "house-robber", "House Robber", "Medium"),
                ("213", "house-robber-ii", "House Robber II", "Medium"),
                ("5", "longest-palindromic-substring", "Longest Palindromic Substring", "Medium"),
                ("322", "coin-change", "Coin Change", "Medium"),
                ("139", "word-break", "Word Break", "Medium"),
                ("300", "longest-increasing-subsequence", "Longest Increasing Subsequence", "Medium"),
                ("416", "partition-equal-subset-sum", "Partition Equal Subset Sum", "Medium"),
            ]),
            ("2-D Dynamic Programming", [
                ("62", "unique-paths", "Unique Paths", "Medium"),
                ("1143", "longest-common-subsequence", "Longest Common Subsequence", "Medium"),
                ("518", "coin-change-ii", "Coin Change II", "Medium"),
                ("494", "target-sum", "Target Sum", "Medium"),
                ("72", "edit-distance", "Edit Distance", "Medium"),
                ("312", "burst-balloons", "Burst Balloons", "Hard"),
            ]),
            ("Greedy", [
                ("53", "maximum-subarray", "Maximum Subarray", "Medium"),
                ("55", "jump-game", "Jump Game", "Medium"),
                ("45", "jump-game-ii", "Jump Game II", "Medium"),
                ("134", "gas-station", "Gas Station", "Medium"),
                ("846", "hand-of-straights", "Hand of Straights", "Medium"),
                ("763", "partition-labels", "Partition Labels", "Medium"),
            ]),
            ("Intervals", [
                ("57", "insert-interval", "Insert Interval", "Medium"),
                ("56", "merge-intervals", "Merge Intervals", "Medium"),
                ("435", "non-overlapping-intervals", "Non-overlapping Intervals", "Medium"),
            ]),
            ("Math & Geometry", [
                ("202", "happy-number", "Happy Number", "Easy"),
                ("48", "rotate-image", "Rotate Image", "Medium"),
                ("54", "spiral-matrix", "Spiral Matrix", "Medium"),
                ("73", "set-matrix-zeroes", "Set Matrix Zeroes", "Medium"),
                ("50", "powx-n", "Pow(x, n)", "Medium"),
            ]),
            ("Bit Manipulation", [
                ("136", "single-number", "Single Number", "Easy"),
                ("191", "number-of-1-bits", "Number of 1 Bits", "Easy"),
                ("338", "counting-bits", "Counting Bits", "Easy"),
                ("190", "reverse-bits", "Reverse Bits", "Easy"),
                ("268", "missing-number", "Missing Number", "Easy"),
                ("371", "sum-of-two-integers", "Sum of Two Integers", "Medium"),
            ]),
        ],
    },
    {
        "id": "beginner-foundations",
        "name": "Beginner Foundations",
        "description": "Gentle easy problems that build fluency with loops, arrays, strings, linked lists, "
                       "trees and first steps in recursion before tackling interview patterns.",
        "patterns": [
            ("Warm-up & Math", [
                ("412", "fizz-buzz", "Fizz Buzz", "Easy"),
                ("1480", "running-sum-of-1d-array", "Running Sum of 1d Array", "Easy"),
                ("1672", "richest-customer-wealth", "Richest Customer Wealth", "Easy"),
                ("1342", "number-of-steps-to-reduce-a-number-to-zero", "Number of Steps to Reduce a Number to Zero", "Easy"),
                ("9", "palindrome-number", "Palindrome Number", "Easy"),
                ("66", "plus-one", "Plus One", "Easy"),
            ]),
            ("Arrays", [
                ("26", "remove-duplicates-from-sorted-array", "Remove Duplicates from Sorted Array", "Easy"),
                ("27", "remove-element", "Remove Element", "Easy"),
                ("35", "search-insert-position", "Search Insert Position", "Easy"),
                ("88", "merge-sorted-array", "Merge Sorted Array", "Easy"),
                ("169", "majority-element", "Majority Element", "Easy"),
                ("283", "move-zeroes", "Move Zeroes", "Easy"),
                ("448", "find-all-numbers-disappeared-in-an-array", "Find All Numbers Disappeared in an Array", "Easy"),
                ("977", "squares-of-a-sorted-array", "Squares of a Sorted Array", "Easy"),
                ("1365", "how-many-numbers-are-smaller-than-the-current-number", "How Many Numbers Are Smaller Than the Current Number", "Easy"),
            ]),
            ("Strings", [
                ("13", "roman-to-integer", "Roman to Integer", "Easy"),
                ("14", "longest-common-prefix", "Longest Common Prefix", "Easy"),
                ("58", "length-of-last-word", "Length of Last Word", "Easy"),
                ("344", "reverse-string", "Reverse String", "Easy"),
                ("383", "ransom-note", "Ransom Note", "Easy"),
                ("387", "first-unique-character-in-a-string", "First Unique Character in a String", "Easy"),
                ("205", "isomorphic-strings", "Isomorphic Strings", "Easy"),
                ("392", "is-subsequence", "Is Subsequence", "Easy"),
            ]),
            ("Hashing & Sets", [
                ("349", "intersection-of-two-arrays", "Intersection of Two Arrays", "Easy"),
                ("771", "jewels-and-stones", "Jewels and Stones", "Easy"),
                ("1512", "number-of-good-pairs", "Number of Good Pairs", "Easy"),
            ]),
            ("Linked List", [
                ("876", "middle-of-the-linked-list", "Middle of the Linked List", "Easy"),
                ("203", "remove-linked-list-elements", "Remove Linked List Elements", "Easy"),
                ("234", "palindrome-linked-list", "Palindrome Linked List", "Easy"),
            ]),
            ("Trees", [
                ("94", "binary-tree-inorder-traversal", "Binary Tree Inorder Traversal", "Easy"),
                ("101", "symmetric-tree", "Symmetric Tree", "Easy"),
                ("108", "convert-sorted-array-to-binary-search-tree", "Convert Sorted Array to Binary Search Tree", "Easy"),
            ]),
            ("Recursion & First DP", [
                ("509", "fibonacci-number", "Fibonacci Number", "Easy"),
                ("118", "pascals-triangle", "Pascal's Triangle", "Easy"),
            ]),
        ],
    },
]

_BY_ID = {c["id"]: c for c in CURRICULA}


def all_problems(curriculum: Dict[str, Any]) -> List[Problem]:
    return [p for _, problems in curriculum["patterns"] for p in problems]


def list_curricula() -> List[Dict[str, Any]]:
    return [
        {
            "id": c["id"],
            "name": c["name"],
            "description": c["description"],
            "problem_count": len(all_problems(c)),
            "patterns": [name for name, _ in c["patterns"]],
        }
        for c in CURRICULA
    ]


def get_curriculum(curriculum_id: str) -> Optional[Dict[str, Any]]:
    return _BY_ID.get(curriculum_id)


def import_curriculum(db: Database, user_id: str, curriculum_id: str, tracked: Dict[str, str]) -> Dict[str, Any]:
    """Create root folder + one subfolder per pattern + questions for untracked problems."""
    c = get_curriculum(curriculum_id)
    if not c:
        raise HTTPException(status_code=404, detail="Curriculum not found")

    pending: List[Tuple[str, List[Problem]]] = []
    seen = set(tracked.keys())
    for pattern, problems in c["patterns"]:
        fresh = []
        for p in problems:
            if p[1] not in seen:
                seen.add(p[1])
                fresh.append(p)
        if fresh:
            pending.append((pattern, fresh))

    if not pending:
        existing = db.folders.find_one({"user_id": user_id, "parent_id": None, "name": c["name"]}, {"_id": 0, "id": 1})
        if existing:
            return {"folder_id": existing["id"], "folder_name": c["name"], "questions_imported": 0}
        raise HTTPException(status_code=409, detail="You already track every problem in this curriculum.")

    root = new_folder_doc(user_id, c["name"], None, next_position(db, "folders", {"user_id": user_id, "parent_id": None}),
                          description=c["description"])
    folders = [root]
    questions: List[Dict[str, Any]] = []
    for idx, (pattern, problems) in enumerate(pending):
        sub = new_folder_doc(user_id, pattern, root["id"], idx)
        folders.append(sub)
        for pos, (fid, slug, title, difficulty) in enumerate(problems):
            questions.append(new_question_doc(
                user_id,
                folder_id=sub["id"],
                title=title,
                problem_url=_url(slug),
                difficulty=difficulty,
                tags=[pattern],
                position=pos,
                leetcode_slug=slug,
                leetcode_id=fid,
            ))
    db.folders.insert_many(folders)
    db.questions.insert_many(questions)
    return {"folder_id": root["id"], "folder_name": root["name"], "questions_imported": len(questions)}
