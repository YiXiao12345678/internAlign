"""
Shared skill taxonomy used by both the job-posting parser and the resume
gap analysis, so both sides agree on what counts as a skill.

Why this exists
---------------
The first version matched skills with a plain word-boundary regex, which gave
false positives that polluted the analysis:

  * "c" matched inside "c++" and "c/c++"
  * "go" matched the English verb ("excited to go on this journey")

Each skill now has:
  * aliases        - other spellings that mean the same thing
  * related        - skills that count as *partial* evidence (e.g. PyTorch
                     is related to machine learning)
  * a matcher that refuses to match inside longer tokens such as "c++" or
    "node.js", and only accepts ambiguous words like "go" in a list/tech context.
"""
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Skill:
    name: str                                   # canonical, lowercase
    category: str                               # language | cloud | data | ml | web | tools | concept | hardware
    aliases: tuple[str, ...] = ()
    related: tuple[str, ...] = ()               # canonical names that give partial credit
    display: str = ""                           # pretty name for the UI

    @property
    def label(self) -> str:
        return self.display or self.name.title()


def _s(name, category, aliases=(), related=(), display=""):
    return Skill(name, category, tuple(aliases), tuple(related), display)


SKILLS: list[Skill] = [
    # Languages
    _s("python", "language", ["python3", "py"], ["pandas", "numpy"], "Python"),
    _s("java", "language", [], ["kotlin", "c#"], "Java"),
    _s("c", "language", [], ["c++"], "C"),
    _s("c++", "language", ["cpp"], ["c"], "C++"),
    _s("c#", "language", ["csharp", "c sharp"], ["java"], "C#"),
    _s("sql", "language", [], ["mysql", "postgresql", "sqlite"], "SQL"),
    _s("javascript", "language", ["js", "ecmascript", "es6"], ["typescript", "react", "node.js"], "JavaScript"),
    _s("typescript", "language", [], ["javascript"], "TypeScript"),
    _s("go", "language", ["golang"], [], "Go"),
    _s("rust", "language", [], [], "Rust"),
    _s("kotlin", "language", [], ["java"], "Kotlin"),
    _s("swift", "language", [], [], "Swift"),
    _s("scala", "language", [], ["java", "spark"], "Scala"),
    _s("ruby", "language", [], [], "Ruby"),
    _s("php", "language", [], [], "PHP"),
    _s("bash", "language", ["shell scripting", "shell script", "shell"], ["linux"], "Bash / shell"),
    _s("matlab", "language", [], ["python"], "MATLAB"),
    _s("verilog", "hardware", ["systemverilog", "vhdl"], [], "Verilog / HDL"),
    # Tools / infra
    _s("git", "tools", ["github", "gitlab", "version control"], [], "Git"),
    _s("linux", "tools", ["unix"], ["bash"], "Linux"),
    _s("docker", "tools", ["containers", "containerization"], ["kubernetes"], "Docker"),
    _s("kubernetes", "tools", ["k8s"], ["docker"], "Kubernetes"),
    _s("terraform", "tools", ["infrastructure as code"], [], "Terraform"),
    _s("ci/cd", "tools", ["cicd", "continuous integration", "github actions", "jenkins"], ["git"], "CI/CD"),
    # Cloud
    _s("aws", "cloud", ["amazon web services", "ec2", "s3 bucket"], ["gcp", "azure"], "AWS"),
    _s("gcp", "cloud", ["google cloud", "google cloud platform"], ["aws", "azure"], "GCP"),
    _s("azure", "cloud", ["microsoft azure"], ["aws", "gcp"], "Azure"),
    # Data
    _s("pandas", "data", [], ["python", "numpy"], "pandas"),
    _s("numpy", "data", [], ["python", "pandas"], "NumPy"),
    _s("spark", "data", ["pyspark", "apache spark"], ["hadoop", "hive"], "Spark"),
    _s("hadoop", "data", [], ["spark", "hive"], "Hadoop"),
    _s("hive", "data", [], ["hadoop", "sql"], "Hive"),
    _s("kafka", "data", ["apache kafka"], [], "Kafka"),
    _s("airflow", "data", ["apache airflow"], [], "Airflow"),
    _s("postgresql", "data", ["postgres"], ["sql", "mysql"], "PostgreSQL"),
    _s("mysql", "data", [], ["sql", "postgresql"], "MySQL"),
    _s("mongodb", "data", ["mongo"], [], "MongoDB"),
    _s("redis", "data", [], [], "Redis"),
    _s("power bi", "data", ["powerbi"], ["tableau", "excel"], "Power BI"),
    _s("tableau", "data", [], ["power bi"], "Tableau"),
    # ML
    _s("machine learning", "ml", ["ml"], ["pytorch", "tensorflow", "scikit-learn", "deep learning"], "Machine learning"),
    _s("deep learning", "ml", [], ["pytorch", "tensorflow", "machine learning"], "Deep learning"),
    _s("pytorch", "ml", ["torch"], ["tensorflow", "deep learning"], "PyTorch"),
    _s("tensorflow", "ml", ["keras"], ["pytorch", "deep learning"], "TensorFlow"),
    _s("scikit-learn", "ml", ["sklearn", "scikit learn"], ["machine learning"], "scikit-learn"),
    _s("nlp", "ml", ["natural language processing"], ["machine learning", "llm"], "NLP"),
    _s("llm", "ml", ["llms", "large language model", "large language models", "generative ai"], ["nlp", "machine learning"], "LLMs"),
    _s("computer vision", "ml", [], ["deep learning", "machine learning"], "Computer vision"),
    # Web / backend
    _s("react", "web", ["react.js", "reactjs"], ["javascript", "typescript"], "React"),
    _s("node.js", "web", ["nodejs", "node js"], ["javascript", "typescript"], "Node.js"),
    _s("django", "web", [], ["python", "flask", "fastapi"], "Django"),
    _s("flask", "web", [], ["python", "django", "fastapi"], "Flask"),
    _s("fastapi", "web", [], ["python", "flask", "django"], "FastAPI"),
    _s("spring boot", "web", ["spring framework"], ["java"], "Spring Boot"),
    _s("rest api", "web", ["rest apis", "restful", "restful api", "restful apis", "rest"], ["flask", "fastapi", "django", "node.js", "spring boot"], "REST APIs"),
    _s("graphql", "web", [], ["rest api"], "GraphQL"),
    _s("html/css", "web", ["html", "css", "html5", "css3"], ["javascript", "react"], "HTML/CSS"),
    # CS concepts
    _s("data structures", "concept", ["data structure"], ["algorithms"], "Data structures"),
    _s("algorithms", "concept", ["algorithm"], ["data structures"], "Algorithms"),
    _s("object-oriented programming", "concept", ["oop", "object oriented", "object-oriented"], ["java", "c++", "python"], "Object-oriented programming"),
    _s("operating systems", "concept", ["operating system"], ["linux"], "Operating systems"),
    _s("distributed systems", "concept", [], ["kafka", "kubernetes"], "Distributed systems"),
    _s("unit testing", "concept", ["unit tests", "pytest", "junit"], ["test automation"], "Unit testing"),
    _s("test automation", "concept", ["automated testing", "test automation framework"], ["unit testing", "python"], "Test automation"),
    _s("debugging", "concept", [], [], "Debugging"),
    _s("agile", "concept", ["scrum", "kanban"], [], "Agile"),
    # Hardware / test (relevant to RF / validation-style internships)
    _s("embedded systems", "hardware", ["embedded system", "embedded software", "firmware", "rtos"], ["c", "c++"], "Embedded systems"),
    _s("wireless", "hardware", ["rf", "bluetooth", "wi-fi", "wifi", "5g", "lte"], [], "Wireless / RF"),
    _s("labview", "hardware", [], ["matlab", "test automation"], "LabVIEW"),
    _s("excel", "tools", ["microsoft excel"], ["power bi", "tableau"], "Excel"),
]

SKILL_BY_NAME: dict[str, Skill] = {s.name: s for s in SKILLS}

# Tokens that are also ordinary English words. These only count when they
# appear in a technical context (inside a list, or after "in/with/using").
_AMBIGUOUS = {"go", "rest", "py", "ml", "rf", "shell", "containers", "swift", "react"}

# For ambiguous tokens: words that, when they directly follow, mean it is just English.
_ENGLISH_NEXT = r"(?:to|through|on|ahead|the|a|an|for|with|from|into|about|over|up|out|back|live|fast|quickly|well|and\s+respond)"

# A token is "inside" something larger if adjacent to these characters.
# (Lets "c" ignore "c++"/"c#", and "java" ignore "java.util"... but allow "c/c++".)
_LEFT_GUARD = r"(?<![\w+#.\-])"
_RIGHT_GUARD = r"(?![\w+#\-])(?!\.\w)"

_PREV_TECH_WORD = r"(?:in|with|using|and|or|like|including|as|of|via|plus|use)"


# Ambiguous aliases are checked with a small hand-written function (looking at
# what comes before/after) instead of a single regex.
def _ambiguous_hit(alias: str, text: str) -> bool:
    body = re.escape(alias)
    for m in re.finditer(_LEFT_GUARD + body + _RIGHT_GUARD, text, re.IGNORECASE):
        before = text[: m.start()].rstrip(" \t")
        after = text[m.end():]
        in_list = before.endswith((",", "/", "(", ";", ":", "\n")) or before == ""
        if not in_list:
            prev_word = re.search(r"([A-Za-z]+)$", before)
            in_list = bool(prev_word and re.fullmatch(_PREV_TECH_WORD, prev_word.group(1), re.IGNORECASE))
        english = re.match(rf"\s+{_ENGLISH_NEXT}\b", after, re.IGNORECASE)
        # A following comma/slash/"or" strongly suggests a list of technologies.
        list_after = re.match(r"\s*(?:,|/|\)|\bor\b|\band\b)", after, re.IGNORECASE)
        if (in_list or list_after) and not english:
            return True
    return False


def _flexible(alias: str) -> str:
    """Escape an alias, letting spaces/hyphens inside it match each other
    ("deep learning" also matches "deep-learning"; "scikit-learn" matches "scikit learn")."""
    parts = re.split(r"([\s\-]+)", alias)
    out = []
    for part in parts:
        if part and re.fullmatch(r"[\s\-]+", part):
            out.append(r"[\s\-]+" if " " in part else r"[\s\-]?")
        else:
            out.append(re.escape(part))
    return "".join(out)


def _plain_matcher(alias: str) -> re.Pattern:
    return re.compile(_LEFT_GUARD + _flexible(alias) + _RIGHT_GUARD, re.IGNORECASE)


_PLAIN: dict[str, list[tuple[str, re.Pattern | None]]] = {}
for _skill in SKILLS:
    entries = []
    for _alias in (_skill.name, *_skill.aliases):
        if _alias in _AMBIGUOUS:
            entries.append((_alias, None))        # handled by _ambiguous_hit
        else:
            entries.append((_alias, _plain_matcher(_alias)))
    _PLAIN[_skill.name] = entries


def mentions(skill_name: str, text: str) -> bool:
    """True if `text` mentions the skill (or any alias) in a technical sense."""
    for alias, pattern in _PLAIN[skill_name]:
        if pattern is None:
            if _ambiguous_hit(alias, text):
                return True
        elif pattern.search(text):
            return True
    return False


def find_skills(text: str) -> list[str]:
    """Canonical names of all skills mentioned in `text`, sorted."""
    return sorted(s.name for s in SKILLS if mentions(s.name, text))


def label(skill_name: str) -> str:
    skill = SKILL_BY_NAME.get(skill_name)
    return skill.label if skill else skill_name
