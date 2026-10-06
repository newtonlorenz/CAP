"""Optional, local OpenDataLoader boundary, executed only inside the PDF worker.

The pinned wheel supplies the JAR and its licences. No hybrid server, model download
or external document processing is used. The outer worker owns the process group.
"""

import importlib.resources
import importlib.util
import json
import re
import shutil
import subprocess
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path


ENGINE_VERSION = "2.5.11"
PIPELINE_VERSION = "opendataloader_v1"
MAX_OUTPUT_BYTES = 32 * 1024 * 1024
JAVA_LIMITS = (
    "-Xms32m", "-Xmx512m", "-XX:MaxMetaspaceSize=128m",
    "-XX:CompressedClassSpaceSize=64m", "-XX:ReservedCodeCacheSize=64m",
    "-XX:+UseSerialGC",
)


def structured_pdf_available() -> bool:
    if importlib.util.find_spec("opendataloader_pdf") is None:
        return False
    try:
        if version("opendataloader-pdf") != ENGINE_VERSION:
            return False
    except PackageNotFoundError:
        return False

    java = shutil.which("java")
    if not java:
        return False
    try:
        result = subprocess.run(
            [java, *JAVA_LIMITS, "-version"], capture_output=True, text=True, timeout=3, check=False
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    if result.returncode != 0:
        return False
    match = re.search(r'(?:openjdk|java) version "(\d+)(?:\.(\d+))?', result.stderr + result.stdout)
    if not match:
        return False
    major = int(match.group(2)) if match.group(1) == "1" and match.group(2) else int(match.group(1))
    return major >= 17


def read_structured_pdf(source: str, output_dir: str, *, timeout: int) -> dict:
    if not structured_pdf_available():
        raise ValueError(
            f"Structured PDF import requires OpenDataLoader {ENGINE_VERSION} and Java 17 or later."
        )
    jar = importlib.resources.files("opendataloader_pdf").joinpath(
        "jar", "opendataloader-pdf-cli.jar"
    )
    with importlib.resources.as_file(jar) as jar_path:
        try:
            subprocess.run(
                [
                    "java", *JAVA_LIMITS, "-Djava.awt.headless=true", "-Dapple.awt.UIElement=true",
                    "-jar", str(jar_path), "--format", "json", "--output-dir", output_dir,
                    str(Path(source).resolve()),
                ],
                check=True, timeout=timeout,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
        except (subprocess.SubprocessError, OSError) as exc:
            raise ValueError("Structured PDF extraction failed or exceeded its time limit.") from exc
    outputs = list(Path(output_dir).glob("*.json"))
    if len(outputs) != 1 or outputs[0].stat().st_size > MAX_OUTPUT_BYTES:
        raise ValueError("Structured PDF output is missing or exceeds the safe processing limit.")
    payload = json.loads(outputs[0].read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not isinstance(payload.get("kids"), list):
        raise ValueError("Structured PDF output has an unsupported format.")
    return payload
