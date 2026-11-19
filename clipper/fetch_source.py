def _pot_args() -> list[str]:
    if not _pot_provider_ready():
        common.warn("pot_provider_unreachable", host=POT_HOST, port=POT_PORT)
        return []
    common.info("using_pot_provider", url=f"http://{POT_HOST}:{POT_PORT}")
    return [
        "--extractor-args",
        "youtube:player_client=mweb,tv,web_safari;fetch_pot=always",
        "--extractor-args",
        f"youtubepot-bgutilhttp:base_url=http://{POT_HOST}:{POT_PORT}",
    ]
