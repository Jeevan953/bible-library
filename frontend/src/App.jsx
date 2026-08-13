import { useEffect, useState } from "react";

import AboutPage from "./AboutPage";
import BibleReader from "./BibleReader";
import HomePage from "./HomePage";
import ParallelReader from "./ParallelReader";
import SearchPage from "./SearchPage";
import { getVersions } from "./services/bibleApi";

import "./App.css";
import "./VersionNotice.css";

const MEDIA_URL = (
  import.meta.env.VITE_MEDIA_URL ||
  (import.meta.env.DEV
    ? "http://127.0.0.1:8000/media"
    : "")
).replace(/\/+$/, "");

function App() {
  const [page, setPage] = useState("home");
  const [versions, setVersions] = useState([]);
  const [selectedVersion, setSelectedVersion] = useState(null);
  const [readerLocation, setReaderLocation] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const availableVersions = versions.filter(
    (version) => version.available,
  );

  useEffect(() => {
    async function loadVersions() {
      try {
        const data = await getVersions();
        setVersions(data);
      } catch (requestError) {
        setError(requestError.message);
      } finally {
        setLoading(false);
      }
    }

    loadVersions();
  }, []);

  function returnHome(event) {
    event?.preventDefault();

    setPage("home");
    setSelectedVersion(null);
    setReaderLocation(null);

    window.history.replaceState(null, "", "#home");
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  function openAbout(event) {
    event?.preventDefault();

    setPage("about");
    setSelectedVersion(null);
    setReaderLocation(null);

    window.history.replaceState(null, "", "#about");
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  function openVersions(event) {
    event?.preventDefault();

    setPage("versions");
    setSelectedVersion(null);
    setReaderLocation(null);

    window.history.replaceState(null, "", "#versions");

    requestAnimationFrame(() => {
      requestAnimationFrame(() => {
        document.getElementById("versions")?.scrollIntoView({
          behavior: "smooth",
          block: "start",
        });
      });
    });
  }

  function openVersion(version) {
    setPage("reader");
    setSelectedVersion(version);
    setReaderLocation(null);

    window.history.replaceState(null, "", "#reader");
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  function openReader(event) {
    event?.preventDefault();

    const readerVersion =
      availableVersions.find(
        (version) => version.abbreviation === "KJV",
      ) || availableVersions[0];

    if (!readerVersion) {
      return;
    }

    openVersion(readerVersion);
  }

  function openTamilBible() {
    const tamilVersion = availableVersions.find(
      (version) => version.abbreviation === "PPTB1856",
    );

    if (!tamilVersion) {
      return;
    }

    openVersion(tamilVersion);
  }

  function openSearch(event) {
    event?.preventDefault();

    setPage("search");
    setSelectedVersion(null);
    setReaderLocation(null);

    window.history.replaceState(null, "", "#search");
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  function openParallel(event) {
    event?.preventDefault();

    setPage("parallel");
    setSelectedVersion(null);
    setReaderLocation(null);

    window.history.replaceState(null, "", "#parallel");
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  function openSearchResult(abbreviation, result) {
    const version = versions.find(
      (item) => item.abbreviation === abbreviation,
    );

    if (!version) {
      return;
    }

    setReaderLocation({
      bookPosition: result.book.position,
      chapter: result.chapter,
      verse: result.verse,
    });

    setSelectedVersion(version);
    setPage("reader");

    window.history.replaceState(null, "", "#reader");
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  return (
    <div className="app">
      <header className="site-header">
        <div>
          <span className="brand-mark">✝</span>
          <span className="brand">Know Your Bible</span>
        </div>

        <nav>
          <a href="#home" onClick={returnHome}>
            Home
          </a>

          <a href="#about" onClick={openAbout}>
            About
          </a>

          <a href="#versions" onClick={openVersions}>
            Versions
          </a>

          <a href="#reader" onClick={openReader}>
            Reader
          </a>

          <a href="#search" onClick={openSearch}>
            Search
          </a>

          <a href="#parallel" onClick={openParallel}>
            Parallel
          </a>
        </nav>
      </header>

      <main>
        {page === "home" ? (
          <HomePage
            versions={versions}
            onBrowseVersions={openVersions}
            onOpenTamil={openTamilBible}
            onOpenAbout={openAbout}
          />
        ) : page === "about" ? (
          <AboutPage onBack={returnHome} />
        ) : page === "search" ? (
          <SearchPage
            versions={availableVersions}
            onOpenResult={openSearchResult}
            onBack={returnHome}
          />
        ) : page === "parallel" ? (
          <ParallelReader
            versions={availableVersions}
            onBack={returnHome}
          />
        ) : page === "reader" && selectedVersion ? (
          <BibleReader
            version={selectedVersion}
            versions={availableVersions}
            initialLocation={readerLocation}
            onVersionChange={(version) => {
              setSelectedVersion(version);
              setReaderLocation(null);
            }}
            onBack={returnHome}
          />
        ) : (
          <section
            className="versions-section"
            id="versions"
          >
            <div className="section-heading">
              <div>
                <p className="eyebrow">
                  Available translations
                </p>

                <h2>Bible Versions</h2>
              </div>

              {!loading && (
                <span className="version-count">
                  {versions.length} versions
                </span>
              )}
            </div>

            {loading && (
              <p className="status">
                Loading Bible versions…
              </p>
            )}

            {error && (
              <p className="status error">{error}</p>
            )}

            <div className="version-grid">
              {versions.map((version) => (
                <article
                  className="version-card"
                  key={version.id}
                >
                  <div className="version-top">
                    <span className="abbreviation">
                      {version.abbreviation}
                    </span>

                    <span className="language">
                      {version.language}
                    </span>
                  </div>

                  <h3>{version.name}</h3>

                  <p className="year">
                    {version.year
                      ? `Published ${version.year}`
                      : "Year unknown"}
                  </p>

                  {version.description && (
                    <details
                      className="version-notice"
                      open={version.abbreviation === "OTCV"}
                    >
                      <summary>
                        Copyright, source &amp; license
                      </summary>

                      <p>{version.description}</p>
                    </details>
                  )}

                  <button
                    type="button"
                    disabled={!version.available}
                    onClick={() => openVersion(version)}
                  >
                    {version.available
                      ? "Open Bible"
                      : "Text not imported"}
                  </button>

                  {MEDIA_URL && version.pdf_filename && (
                    <a
                      className="pdf-button"
                      href={`${MEDIA_URL}/${encodeURIComponent(
                        version.pdf_filename,
                      )}`}
                      target="_blank"
                      rel="noopener noreferrer"
                    >
                      View PDF
                    </a>
                  )}
                </article>
              ))}
            </div>
          </section>
        )}
      </main>

      <footer className="site-license-footer">
        <button
          type="button"
          onClick={openVersions}
        >
          Bible-version copyright, source, and license notices
        </button>
      </footer>
    </div>
  );
}

export default App;
