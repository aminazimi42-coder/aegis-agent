def run(context: dict) -> dict:
    # Simple sample extension that echoes input and adds a tag
    data = context.get("data", "")
    return {"echo": data, "tag": "sample_extension"}
