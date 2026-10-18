import json
from sqlalchemy.orm import Session
from app.models.user import User
from app.models.folder import Folder
from app.models.question import Question
from app.models.solution import Solution
from app.models.bookmark import Bookmark
from app.services.security import hash_password

from typing import Optional

def seed_demo_data(db: Session, target_user: Optional[User] = None) -> User:
    if target_user:
        user = target_user
    else:
        # Check if demo user already exists
        demo_email = "aman@makepattern.dev"
        existing_user = db.query(User).filter(User.email == demo_email).first()
        if existing_user:
            return existing_user

        # Create user
        user = User(
            email=demo_email,
            full_name="Aman Kumar",
            hashed_password=hash_password("password123")
        )
        db.add(user)
        db.commit()
        db.refresh(user)

    # 1. Root Folder: Beginner Problems & DSA
    beginner_root = Folder(user_id=user.id, name="Beginner Problems", parent_id=None, position=0)
    dsa_root = Folder(user_id=user.id, name="DSA", parent_id=None, position=1)
    db.add_all([beginner_root, dsa_root])
    db.commit()
    db.refresh(beginner_root)
    db.refresh(dsa_root)

    # Beginner subcategories
    bp_subfolders = [
        "Fundamentals of Programming",
        "Language Basics",
        "Logic Building (Patterns)",
        "Patterns",
        "Time Complexity",
        "Standard Libraries & Collections",
        "Concept Basics",
        "Basic Maths",
        "Basic Arrays",
        "Basic Hashing",
        "Basic Strings",
        "Basic Recursion"
    ]
    for idx, bp_name in enumerate(bp_subfolders):
        db.add(Folder(user_id=user.id, name=bp_name, parent_id=beginner_root.id, position=idx))
    db.commit()

    # 2. Main Categories under DSA
    arrays = Folder(user_id=user.id, name="Arrays", parent_id=dsa_root.id, position=0)
    sorting = Folder(user_id=user.id, name="Sorting", parent_id=dsa_root.id, position=1)
    strings = Folder(user_id=user.id, name="Strings", parent_id=dsa_root.id, position=2)
    linked_lists = Folder(user_id=user.id, name="Linked Lists", parent_id=dsa_root.id, position=3)
    binary_trees = Folder(user_id=user.id, name="Binary Trees", parent_id=dsa_root.id, position=4)
    graphs = Folder(user_id=user.id, name="Graphs", parent_id=dsa_root.id, position=5)
    dp = Folder(user_id=user.id, name="Dynamic Programming", parent_id=dsa_root.id, position=6)

    db.add_all([arrays, sorting, strings, linked_lists, binary_trees, graphs, dp])
    db.commit()
    db.refresh(arrays)
    db.refresh(sorting)
    db.refresh(binary_trees)
    db.refresh(dp)

    # 3. Subfolders under Arrays
    fundamentals = Folder(user_id=user.id, name="Fundamentals", parent_id=arrays.id, position=0)
    medium_arrays = Folder(user_id=user.id, name="Medium", parent_id=arrays.id, position=1)
    hard_arrays = Folder(user_id=user.id, name="Hard", parent_id=arrays.id, position=2)

    db.add_all([fundamentals, medium_arrays, hard_arrays])
    db.commit()
    db.refresh(fundamentals)
    db.refresh(medium_arrays)

    # 4. Questions with realistic problem statements, notes, and code
    q_two_sum = Question(
        user_id=user.id,
        folder_id=fundamentals.id,
        title="Two Sum",
        difficulty="Easy",
        status="Solved",
        tags=json.dumps(["Array", "Hash Table", "Two Pointers"]),
        position=0,
        problem_statement="Given an array of integers `nums` and an integer `target`, return indices of the two numbers such that they add up to `target`.\n\nYou may assume that each input would have exactly one solution, and you may not use the same element twice.",
        notes="""### 💡 Intuition
To find two numbers summing to target, instead of checking every pair with nested loops, we can check if the complement `target - num` has already been encountered.

### 🚀 Optimal Approach
Use a hash map to store elements as keys and their array indices as values. Iterate through `nums`, calculate complement, and check map presence in $O(1)$ time.

### 📝 Step-by-Step Algorithm
1. Initialize an empty hash map `seen = {}`.
2. For index `i` and value `num` in `nums`:
   - Compute `complement = target - num`.
   - If `complement` in `seen`, return `[seen[complement], i]`.
   - Else, add `seen[num] = i`.
3. Return empty list if no pair matches.

### ⏱️ Complexity
- **Time:** $O(n)$ single pass over array.
- **Space:** $O(n)$ for hash map storage."""
    )

    q_merge_sort = Question(
        user_id=user.id,
        folder_id=sorting.id,
        title="Merge Sort",
        difficulty="Medium",
        status="Solved",
        tags=json.dumps(["Sorting", "Divide and Conquer", "Recursion"]),
        position=0,
        problem_statement="Given an array of integers `nums`, sort the array in ascending order using the Merge Sort algorithm.",
        notes="""### 💡 Intuition
Divide and conquer strategy: recursively divide the array into halves until subarrays have 1 element, then merge sorted halves back together in linear time.

### 📝 Algorithm
1. Base condition: if len(nums) <= 1, return nums.
2. Find midpoint `mid = len(nums) // 2`.
3. Recursively sort `left = mergeSort(nums[:mid])` and `right = mergeSort(nums[mid:])`.
4. Merge `left` and `right` using two pointer technique.

### ⏱️ Complexity
- **Time:** $O(n \\log n)$ for best, average, and worst cases.
- **Space:** $O(n)$ auxiliary array space."""
    )

    q_tree_traversal = Question(
        user_id=user.id,
        folder_id=binary_trees.id,
        title="Binary Tree Traversal",
        difficulty="Hard",
        status="In Progress",
        tags=json.dumps(["Tree", "DFS", "BFS", "Recursion"]),
        position=0,
        problem_statement="Perform Pre-order, In-order, and Post-order traversals of a given binary tree iteratively and recursively.",
        notes="""### 💡 Traversals Overview
- **Pre-order:** Root -> Left -> Right
- **In-order:** Left -> Root -> Right (produces sorted order in BST!)
- **Post-order:** Left -> Right -> Root

### ⏱️ Complexity
- **Time:** $O(N)$ visit each node once.
- **Space:** $O(H)$ recursion call stack where $H$ is tree height."""
    )

    q_lis = Question(
        user_id=user.id,
        folder_id=dp.id,
        title="Longest Increasing Subsequence",
        difficulty="Medium",
        status="In Progress",
        tags=json.dumps(["Dynamic Programming", "Binary Search", "Array"]),
        position=0,
        problem_statement="Given an integer array `nums`, return the length of the longest strictly increasing subsequence.",
        notes="""### 💡 Approach
Can be solved with DP in $O(n^2)$ or with Patience Sorting + Binary Search in $O(n \\log n)$.

### ⏱️ Complexity
- **Optimal Time:** $O(n \\log n)$ using `bisect_left`.
- **Space:** $O(n)$ for tails array."""
    )

    q_linear_search = Question(
        user_id=user.id,
        folder_id=fundamentals.id,
        title="Linear Search",
        difficulty="Easy",
        status="Solved",
        tags=json.dumps(["Array", "Searching"]),
        position=1,
        problem_statement="Given an array and a key element, find the index of key in the array or return -1.",
        notes="Iterate through each element sequentially and compare with target."
    )

    q_largest = Question(
        user_id=user.id,
        folder_id=fundamentals.id,
        title="Largest Element in Array",
        difficulty="Easy",
        status="Solved",
        tags=json.dumps(["Array", "Fundamentals"]),
        position=2,
        problem_statement="Given an array of integers, find the largest element.",
        notes="Initialize max with first element, iterate and update max."
    )

    q_second_largest = Question(
        user_id=user.id,
        folder_id=fundamentals.id,
        title="Second Largest Element",
        difficulty="Easy",
        status="Solved",
        tags=json.dumps(["Array", "Fundamentals"]),
        position=3,
        problem_statement="Find the second largest distinct element in an array without sorting.",
        notes="Keep track of largest and second_largest in a single pass."
    )

    q_rotate = Question(
        user_id=user.id,
        folder_id=fundamentals.id,
        title="Left Rotate Array by K Places",
        difficulty="Medium",
        status="Needs Revision",
        tags=json.dumps(["Array", "Math"]),
        position=4,
        problem_statement="Rotate an array to the left by `k` steps, where `k` is non-negative.",
        notes="Reverse first `k` elements, reverse remaining elements, then reverse whole array."
    )

    q_quick_sort = Question(
        user_id=user.id,
        folder_id=sorting.id,
        title="Quick Sort",
        difficulty="Medium",
        status="Solved",
        tags=json.dumps(["Sorting", "Divide and Conquer"]),
        position=1,
        problem_statement="Implement Quick Sort with Lomuto or Hoare partitioning."
    )

    # 23 Additional Questions (Unstarted) to complete 32 total questions
    extra_questions = [
        Question(user_id=user.id, folder_id=fundamentals.id, title="Check if Array is Sorted", difficulty="Easy", status=None, position=5),
        Question(user_id=user.id, folder_id=fundamentals.id, title="Remove Duplicates from Sorted Array", difficulty="Easy", status=None, position=6),
        Question(user_id=user.id, folder_id=medium_arrays.id, title="Maximum Subarray (Kadane's)", difficulty="Medium", status=None, position=0),
        Question(user_id=user.id, folder_id=medium_arrays.id, title="Next Permutation", difficulty="Medium", status=None, position=1),
        Question(user_id=user.id, folder_id=medium_arrays.id, title="3Sum", difficulty="Medium", status=None, position=2),
        Question(user_id=user.id, folder_id=medium_arrays.id, title="Subarray Sum Equals K", difficulty="Medium", status=None, position=3),
        Question(user_id=user.id, folder_id=medium_arrays.id, title="Spiral Matrix", difficulty="Medium", status=None, position=4),
        Question(user_id=user.id, folder_id=hard_arrays.id, title="Trapping Rain Water", difficulty="Hard", status=None, position=0),
        Question(user_id=user.id, folder_id=hard_arrays.id, title="Largest Rectangle in Histogram", difficulty="Hard", status=None, position=1),
        Question(user_id=user.id, folder_id=sorting.id, title="Bubble Sort", difficulty="Easy", status=None, position=2),
        Question(user_id=user.id, folder_id=sorting.id, title="Insertion Sort", difficulty="Easy", status=None, position=3),
        Question(user_id=user.id, folder_id=sorting.id, title="Selection Sort", difficulty="Easy", status=None, position=4),
        Question(user_id=user.id, folder_id=strings.id, title="Valid Palindrome", difficulty="Easy", status=None, position=0),
        Question(user_id=user.id, folder_id=strings.id, title="Longest Substring Without Repeating", difficulty="Medium", status=None, position=1),
        Question(user_id=user.id, folder_id=strings.id, title="Group Anagrams", difficulty="Medium", status=None, position=2),
        Question(user_id=user.id, folder_id=linked_lists.id, title="Reverse Linked List", difficulty="Easy", status=None, position=0),
        Question(user_id=user.id, folder_id=linked_lists.id, title="Detect Cycle in Linked List", difficulty="Medium", status=None, position=1),
        Question(user_id=user.id, folder_id=linked_lists.id, title="Merge Two Sorted Lists", difficulty="Easy", status=None, position=2),
        Question(user_id=user.id, folder_id=binary_trees.id, title="Maximum Depth of Binary Tree", difficulty="Easy", status=None, position=1),
        Question(user_id=user.id, folder_id=binary_trees.id, title="Invert Binary Tree", difficulty="Easy", status=None, position=2),
        Question(user_id=user.id, folder_id=graphs.id, title="Number of Islands", difficulty="Medium", status=None, position=0),
        Question(user_id=user.id, folder_id=dp.id, title="Climbing Stairs", difficulty="Easy", status=None, position=1),
        Question(user_id=user.id, folder_id=dp.id, title="Coin Change", difficulty="Medium", status=None, position=2),
    ]

    all_seed_questions = [
        q_two_sum, q_merge_sort, q_tree_traversal, q_lis,
        q_linear_search, q_largest, q_second_largest, q_quick_sort, q_rotate
    ] + extra_questions

    db.add_all(all_seed_questions)
    db.commit()

    for q in all_seed_questions:
        db.refresh(q)

    # 5. Add Solutions with multiple named approaches
    # Two Sum Solutions
    s_two_sum_opt = Solution(
        question_id=q_two_sum.id,
        title="Optimal (Hash Map)",
        language="python",
        code="""def twoSum(nums: list[int], target: int) -> list[int]:
    seen = {}
    for i, num in enumerate(nums):
        diff = target - num
        if diff in seen:
            return [seen[diff], i]
        seen[num] = i
    return []""",
        time_complexity="O(n)",
        space_complexity="O(n)",
        position=0
    )

    s_two_sum_brute = Solution(
        question_id=q_two_sum.id,
        title="Brute Force",
        language="python",
        code="""def twoSum(nums: list[int], target: int) -> list[int]:
    n = len(nums)
    for i in range(n):
        for j in range(i + 1, n):
            if nums[i] + nums[j] == target:
                return [i, j]
    return []""",
        time_complexity="O(n^2)",
        space_complexity="O(1)",
        position=1
    )

    s_two_sum_cpp = Solution(
        question_id=q_two_sum.id,
        title="C++ Optimal",
        language="cpp",
        code="""#include <vector>
#include <unordered_map>

class Solution {
public:
    std::vector<int> twoSum(std::vector<int>& nums, int target) {
        std::unordered_map<int, int> seen;
        for (int i = 0; i < nums.size(); ++i) {
            int complement = target - nums[i];
            if (seen.find(complement) != seen.end()) {
                return {seen[complement], i};
            }
            seen[nums[i]] = i;
        }
        return {};
    }
};""",
        time_complexity="O(n)",
        space_complexity="O(n)",
        position=2
    )

    # Merge Sort Solution
    s_merge_sort = Solution(
        question_id=q_merge_sort.id,
        title="Optimal (Divide & Conquer)",
        language="python",
        code="""def mergeSort(nums: list[int]) -> list[int]:
    if len(nums) <= 1:
        return nums
    mid = len(nums) // 2
    left = mergeSort(nums[:mid])
    right = mergeSort(nums[mid:])
    
    # Merge
    merged = []
    i = j = 0
    while i < len(left) and j < len(right):
        if left[i] <= right[j]:
            merged.append(left[i])
            i += 1
        else:
            merged.append(right[j])
            j += 1
    merged.extend(left[i:])
    merged.extend(right[j:])
    return merged""",
        time_complexity="O(n log n)",
        space_complexity="O(n)",
        position=0
    )

    db.add_all([s_two_sum_opt, s_two_sum_brute, s_two_sum_cpp, s_merge_sort])
    db.commit()

    # 6. Seed Bookmarks (Two Sum, Merge Sort, Binary Tree Traversal)
    b1 = Bookmark(user_id=user.id, question_id=q_two_sum.id)
    b2 = Bookmark(user_id=user.id, question_id=q_merge_sort.id)
    b3 = Bookmark(user_id=user.id, question_id=q_tree_traversal.id)
    db.add_all([b1, b2, b3])
    db.commit()

    return user
