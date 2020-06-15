import confuse

# Singleton config for the app
coverme_config = confuse.LazyConfig('cover.me', __name__)

filename: str = ''

log_name: str = 'default'
