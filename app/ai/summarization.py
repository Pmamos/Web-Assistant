def summarize_text(text: str, max_length: int = 100) -> str:
    """
    Summarizes the given text to a maximum length.

    Args:
        text (str): The text to summarize.
        max_length (int): The maximum length of the summary.

    Returns:
        str: The summarized text.
    """
    if len(text) <= max_length:
        return text
    return text[:max_length] + '...'