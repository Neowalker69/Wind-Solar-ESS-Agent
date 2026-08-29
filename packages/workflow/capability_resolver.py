def resolve_capabilities(plugin_versions: dict[str, str], active_skills: dict[str, str]) -> dict:
    return {"plugins": plugin_versions, "skills": active_skills, "can_read_opcua": "opcua_connector" in plugin_versions}
