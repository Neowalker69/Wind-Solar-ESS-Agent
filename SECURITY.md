# Security Policy

`wind-solar-ESS-Agent` is a personal portfolio and local demonstration project,
not a production security baseline. The default Compose configuration binds the
API and Control UI to `127.0.0.1`; do not expose them directly to a public or
untrusted network.

Never commit `.env`, API keys, database passwords, provider credentials, or
production traces. The container accepts DeepSeek and Bailian credentials from
environment variables or from files referenced by `DEEPSEEK_API_KEY_FILE` and
`DASHSCOPE_API_KEY_FILE`.

For production deployments, inject credentials through the platform secret
manager, rotate leaked credentials immediately, and keep the API gateway behind
TLS and an authenticated reverse proxy.

Security reports should not be opened as public issues. Use GitHub's private
vulnerability reporting feature for this repository when available, or contact
the maintainer privately through <https://github.com/Neowalker69>.
