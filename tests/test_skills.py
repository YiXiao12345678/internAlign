from backend.skills import find_skills


def test_c_does_not_match_inside_cpp():
    assert find_skills("Experience with C++ and Rust") == ["c++", "rust"]


def test_c_slash_cpp_matches_both():
    assert find_skills("experience with c/c++ and scripting") == ["c", "c++"]


def test_go_needs_technical_context():
    assert find_skills("We are excited to go on this journey") == []
    assert find_skills("interns go through base camp") == []
    assert find_skills("primarily using rust, go or c++") == ["c++", "go", "rust"]
    assert find_skills("Languages: Python, Go, SQL") == ["go", "python", "sql"]


def test_aliases_and_hyphens():
    assert find_skills("PySpark, sklearn and deep-learning") == ["deep learning", "scikit-learn", "spark"]
    assert find_skills("built with React.js and nodejs") == ["node.js", "react"]


def test_english_words_are_not_skills():
    assert find_skills("we react quickly to change; the rest of the team") == []
    assert find_skills("Graduating in Spring 2028") == []
