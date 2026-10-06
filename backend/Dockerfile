FROM python:3.12.15-slim@sha256:ddb0207ae1f0356c2b724d740769b0c5f5f51cc54a0525178f721825f78fe74c AS ocr_build
# CAP only reads PNG pages rendered locally by PDFium. Exclude Tesseract's
# optional URL/archive readers and keep compilers out of the runtime image.
RUN apt-get update && apt-get install -y --no-install-recommends \
    cmake g++ make pkg-config libleptonica-dev \
    && rm -rf /var/lib/apt/lists/*
ADD --checksum=sha256:9218e62793116d42a9f6d14cd9348518b27f382096eea3d0f2d1a24616bb5884 \
    https://codeload.github.com/tesseract-ocr/tesseract/tar.gz/refs/tags/5.5.3 /tmp/tesseract.tar.gz
RUN mkdir /tmp/tesseract && tar -xzf /tmp/tesseract.tar.gz -C /tmp/tesseract --strip-components=1 \
    && cmake -S /tmp/tesseract -B /tmp/build \
       -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_PREFIX=/opt/cap-ocr \
       -DBUILD_SHARED_LIBS=OFF -DBUILD_TRAINING_TOOLS=OFF -DBUILD_TESTS=OFF \
       -DDISABLE_CURL=ON -DDISABLE_ARCHIVE=ON -DGRAPHICS_DISABLED=ON \
    && cmake --build /tmp/build --parallel 2 \
    && cmake --install /tmp/build \
    && mkdir -p /opt/cap-ocr/share/licenses/tesseract \
    && cp /tmp/tesseract/LICENSE /opt/cap-ocr/share/licenses/tesseract/LICENSE

FROM python:3.12.15-slim@sha256:ddb0207ae1f0356c2b724d740769b0c5f5f51cc54a0525178f721825f78fe74c AS core
ARG VCS_REF=unknown
LABEL org.opencontainers.image.revision=$VCS_REF
WORKDIR /app
RUN apt-get update && apt-get upgrade -y \
    && apt-get install -y --no-install-recommends postgresql-client \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 10001 cap && useradd --uid 10001 --gid cap --no-create-home cap
COPY pyproject.toml requirements.lock ./
RUN pip install --no-cache-dir --require-hashes -r requirements.lock
COPY app ./app
COPY alembic ./alembic
COPY alembic.ini start-web.sh ./
RUN chmod +x start-web.sh && mkdir -p /app/uploads && chown cap:cap /app/uploads
USER cap
EXPOSE 8000
CMD ["sh", "./start-web.sh"]

# Opt in with docker-compose.ocr.yml; the standard image has no OCR executable.
FROM core AS ocr
ARG OCR_LANGUAGE_PACKAGES="tesseract-ocr-eng"
USER root
RUN apt-get update && apt-get install -y --no-install-recommends \
    libleptonica6 libstdc++6 ${OCR_LANGUAGE_PACKAGES} \
    && rm -rf /var/lib/apt/lists/*
COPY --from=ocr_build /opt/cap-ocr/bin/tesseract /usr/local/bin/tesseract
COPY --from=ocr_build /opt/cap-ocr/share/tessdata /usr/share/tesseract-ocr/5/tessdata
COPY --from=ocr_build /opt/cap-ocr/share/licenses /usr/local/share/licenses
COPY ocr-build.json /usr/local/share/cap/ocr-build.json
ENV TESSDATA_PREFIX=/usr/share/tesseract-ocr/5/tessdata
RUN tesseract --version && ! ldd /usr/local/bin/tesseract | grep -E 'lib(curl|archive|xml2)'
USER cap

# Local structured PDF extraction. No hybrid server or external model is installed.
FROM core AS structured
USER root
COPY requirements-structured.lock ./
RUN apt-get update && apt-get install -y --no-install-recommends default-jre-headless \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir --require-hashes -r requirements-structured.lock
USER cap

# Both local PDF capabilities for installations that need scanned PDF imports.
FROM structured AS structured_ocr
ARG OCR_LANGUAGE_PACKAGES="tesseract-ocr-eng"
USER root
RUN apt-get update && apt-get install -y --no-install-recommends \
    libleptonica6 libstdc++6 ${OCR_LANGUAGE_PACKAGES} \
    && rm -rf /var/lib/apt/lists/*
COPY --from=ocr_build /opt/cap-ocr/bin/tesseract /usr/local/bin/tesseract
COPY --from=ocr_build /opt/cap-ocr/share/tessdata /usr/share/tesseract-ocr/5/tessdata
COPY --from=ocr_build /opt/cap-ocr/share/licenses /usr/local/share/licenses
COPY ocr-build.json /usr/local/share/cap/ocr-build.json
ENV TESSDATA_PREFIX=/usr/share/tesseract-ocr/5/tessdata
RUN tesseract --version && ! ldd /usr/local/bin/tesseract | grep -E 'lib(curl|archive|xml2)'
USER cap

# Keep the default final target minimal.
FROM core AS runtime
