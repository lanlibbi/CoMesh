FROM nginx:1.27-alpine

# Static assets — single-file Alpine frontend, no build step.
# Every page here is expected to be styled by style.css + app.js only.
COPY index.html login.html register.html credits.html chat.html pool.html nodes.html earnings.html agent.html profile.html usage.html admin-usage.html /usr/share/nginx/html/
COPY app.js style.css /usr/share/nginx/html/
COPY pool.js nodes.js earnings.js agent.js profile.js usage.js admin-usage.js i18n.js /usr/share/nginx/html/

# Nginx config
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80
