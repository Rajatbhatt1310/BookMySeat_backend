from urllib.parse import urlparse, parse_qs


def get_youtube_embed_url(url):
    """
    Converts a normal youtube URL into an embeddable iframe URL and returns none if url is empty.....
    """

    if not url:
        return None

    parsed_url = urlparse(url)

    
    if "youtube.com" in parsed_url.netloc:
        video_id = parse_qs(parsed_url.query).get("v")

        if video_id:
            return f"https://www.youtube.com/embed/{video_id[0]}"

    
    if "youtu.be" in parsed_url.netloc:
        video_id = parsed_url.path.strip("/")

        if video_id:
            return f"https://www.youtube.com/embed/{video_id}"

    return None