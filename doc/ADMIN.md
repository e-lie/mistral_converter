## Mistral API key

Each user enters their own Mistral API key on the app page. It is stored under the data directory, readable by the app user only.

## Backups

The data directory (uploaded PDFs, conversion results and users' API keys) is included in backups; use `--no-data` to leave it out.

## Install and upgrade

The repository must be public: YunoHost clones it without credentials.

    sudo yunohost app install https://github.com/e-lie/mistral_converter
    sudo yunohost app install https://github.com/e-lie/mistral_converter/tree/v0.1.2
    sudo yunohost app install /path/to/mistral_converter

    sudo yunohost app upgrade mistral_converter -u https://github.com/e-lie/mistral_converter
    sudo yunohost app upgrade mistral_converter -u https://github.com/e-lie/mistral_converter/tree/v0.1.2
    sudo yunohost app upgrade mistral_converter -u /path/to/mistral_converter

The deployed version is the git ref given at install or upgrade time. Bump the manifest version (`~ynhN` suffix) by hand.
