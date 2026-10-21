# Loaded as an interactive Bash rcfile, without editing user profiles.
if [ -f /etc/profile ]; then . /etc/profile; fi
if [ -f "$HOME/.bash_profile" ]; then . "$HOME/.bash_profile";
elif [ -f "$HOME/.bash_login" ]; then . "$HOME/.bash_login";
elif [ -f "$HOME/.profile" ]; then . "$HOME/.profile"; fi
if [ -f "$HOME/.bashrc" ]; then . "$HOME/.bashrc"; fi
__ports_prompt() {
    printf '\033]777;ports;%s;ready;%s\007' "$PORTS_TOKEN" "$(printf %s "$PWD" | base64 -w0)"
}
# Append rather than replace existing prompt hooks.
if declare -p PROMPT_COMMAND 2>/dev/null | grep -q 'declare -a'; then
    PROMPT_COMMAND+=(__ports_prompt)
else
    PROMPT_COMMAND="${PROMPT_COMMAND:+$PROMPT_COMMAND; }__ports_prompt"
fi
