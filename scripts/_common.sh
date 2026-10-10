#!/bin/bash

# The app is served below $root_path ("" for a domain root)
set_root_path() {
    if [ "$path" = "/" ]; then root_path=""; else root_path="$path"; fi
}

# Copy the app code from the package directory provided by YunoHost, keeping the venv, env file and caches
copy_app_code() {
    mkdir -p "$install_dir"
    rsync -a --delete \
        --exclude=/.git --exclude=/.venv --exclude=/venv --exclude=/.env --exclude=/env \
        --exclude=/bin --exclude=/.cache --exclude=/.pytest_cache --exclude=__pycache__ --exclude='*.egg-info' \
        --exclude=/scripts --exclude=/conf --exclude=/doc --exclude=/tests \
        --exclude=/manifest.toml --exclude=/config_panel.toml \
        "${1:-$YNH_APP_BASEDIR}/" "$install_dir/"
}

# Install uv and the frozen environment
build_env() {
    ynh_setup_source --dest_dir="$install_dir/bin" --source_id=uv

    chown -R "$app:$app" "$install_dir"
    ynh_exec_as_app env UV_PYTHON_PREFERENCE=only-system UV_PROJECT_ENVIRONMENT="$install_dir/venv" \
        UV_CACHE_DIR="$install_dir/.cache/uv" HOME="$install_dir" \
        "$install_dir/bin/uv" sync --project "$install_dir" --frozen --no-dev --extra web
}

# Install or refresh the app code, uv and the frozen environment
setup_app() {
    copy_app_code
    build_env
}

# Write the config files that depend on settings, then restart the service
apply_config() {
    set_root_path
    ynh_config_add --template="env" --destination="$install_dir/env"
    chmod 600 "$install_dir/env"
    chown "$app:$app" "$install_dir/env"

    ynh_config_add_nginx
    ynh_config_add_systemd
    ynh_config_add_logrotate "/var/log/$app"
}
