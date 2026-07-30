# Watcher Test Suite

> **⚠️ Network Requirement:** You **must** be connected to the University network or active on the institutional VPN to execute tests without triggering rate-limits or firewall blocks.

## ⚙️ Configuration & Setup

* **Configuration (`config.yml`):** Modify `config.yml` in the root directory to define which tests to run and adjust execution parameters (concurrency, strategies, input/output paths).
* **Environment Secrets (`.env`):** Store sensitive credentials in the root `.env` file:

    ```env
    PAGESPEED_API_KEY=your_google_api_key_here
    ```

## 🧪 Available Test Modules

### 1. 🔗 `test_arks`
Verifies ARK URLs to confirm they return expected HTTP status codes, follow proper redirection paths, and correctly match destination target identifiers.
* **Input:** CSV file with ARK links in **Column A**, placed inside the `data/` folder.
* **Output:** Summary results generated in the `output/` directory.

### 2. 🤖 `test_robots`
Audits site routes against crawl rules defined in `data/robots.txt` to verify indexability and bot permissions.
* **Input:** `data/robots.txt` and `data/urls.txt` *(additional URL paths can be appended line-by-line)*.
* **Output:** Validation status logs for tested paths.

### 3. 🖼️ `test_viewers`
Automates browser testing to verify that digital object viewers (e.g., Mirador) initialize correctly and load underlying asset layers/files without breaking.
* **Input:** CSV in `data/` containing the following required headers:
  * `URLs`
  * `Viewer Type`
* **Output:** Detailed pass/fail logs saved in `output/`.

### 4. ⚡ `test_performance`
Runs automated PageSpeed Insights audits across target URLs, collecting comprehensive speed, layout, and accessibility metrics.
* **Features:**
  * **Cold-Start Metric:** Captures an initial `Initial Perf Score (Cold)` before server database and asset caches are primed.
  * **Multi-Pass Averaging:** Runs multiple benchmark passes per URL and averages the performance, accessibility, best practices, SEO, and Core Web Vitals scores.
  * **Stakeholder Glossary:** Appends an executive target metric glossary to the bottom of the CSV output.
* **Requirement:** Ensure `PAGESPEED_API_KEY` is configured in `.env`.
* **Output:** Dated CSV report generated in `output/`.