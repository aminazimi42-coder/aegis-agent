from app.orchestrator import orchestrate_platform


def main() -> None:
    """Entry point for the application runtime."""
    result = orchestrate_platform()
    print(result)


if __name__ == "__main__":
    main()
