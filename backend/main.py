import sys
from backend.resume_parser import extract_resume_text


def main():
    if len(sys.argv) != 2:
        print("Usage: python -m backend.main path/to/resume.pdf")
        return

    resume_path = sys.argv[1]

    try:
        resume_text = extract_resume_text(resume_path)

        if not resume_text:
            print("No text could be extracted from this PDF.")
            return

        print("\nExtracted resume text:\n")
        print(resume_text)

    except Exception as error:
        print(f"Error: {error}")


if __name__ == "__main__":
    main()
