FROM nginx:1.27-alpine

# Static assets — single-file Alpine frontend, no build step.
# Every page here is expected to be styled by style.css + app.js only.
COPY index.html login.html register.html credits.html chat.html pool.html nodes.html agent.html profile.html usage.html admin-usage.html admin-registrations.html /usr/share/nginx/html/
# config.js holds the runtime API base (?api= / localStorage / same-origin).
COPY config.js app.js i18n.js i18n-catalog.js style.css /usr/share/nginx/html/
COPY pool.js nodes.js agent.js profile.js usage.js admin-usage.js admin-registrations.js /usr/share/nginx/html/
COPY particles.js /usr/share/nginx/html/

# Nginx config
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80
