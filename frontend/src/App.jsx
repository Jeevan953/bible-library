import { useEffect, useState } from "react";

import BibleReader from "./BibleReader";
import ParallelReader from "./ParallelReader";
import { getVersions } from "./services/bibleApi";
import SearchPage from "./SearchPage";
import "./App.css";

const MEDIA_URL =
  import.meta.env.VITE_MEDIA_URL ||
  (import.meta.env.DEV
    ? "http://127.0.0.1:8000/media"
    : "");

function App() {
  const [versions, setVersions] = useState([]);
  const [selectedVersion, setSelectedVersion] = useState(null);
  const [readerLocation, setReaderLocation] = useState(null);
  const [showParallel, setShowParallel] = useState(false);
  const [showSearch, setShowSearch] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");


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


  function returnHome() {
    setSelectedVersion(null);
    setError("");
    setShowParallel(false);
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

  setShowSearch(false);
  setShowParallel(false);
  setSelectedVersion(version);

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
          <a href="#versions" onClick={returnHome}>
            Versions
          </a>

          <a
  href="#reader"
  onClick={(event) => {
    event.preventDefault();

    const readerVersion =
      versions.find(
        (item) => item.abbreviation === "KJV" && item.available
      ) || versions.find((item) => item.available);

    setShowSearch(false);
    setShowParallel(false);
    setReaderLocation(null);
    setSelectedVersion(readerVersion || null);
    window.scrollTo({ top: 0, behavior: "smooth" });
  }}
>
  Reader
</a>

         <a
  href="#search"
  onClick={(event) => {
    event.preventDefault();
    setSelectedVersion(null);
    setReaderLocation(null);
    setShowParallel(false);
    setShowSearch(true);
    window.scrollTo({ top: 0, behavior: "smooth" });
  }}
>
  Search
</a>
          <a
  href="#parallel"
  onClick={(event) => {
    event.preventDefault();
    setSelectedVersion(null);
    setReaderLocation(null);
    setShowParallel(true);
    setShowSearch(false);
    window.scrollTo({ top: 0, behavior: "smooth" });
  }}
>
  Parallel
</a>
        </nav>
      </header>

      <main>
  {showSearch ? (
    <SearchPage
      versions={versions.filter((item) => item.available)}
      onOpenResult={openSearchResult}
      onBack={returnHome}
    />
  ) : showParallel ? (
    <ParallelReader
      versions={versions.filter((item) => item.available)}
      onBack={returnHome}
    />
  ) : selectedVersion ? (
    <BibleReader
      version={selectedVersion}
      versions={versions.filter((item) => item.available)}
      initialLocation={readerLocation}
      onVersionChange={setSelectedVersion}
      onBack={returnHome}
    />
  ) : (
    <>
            <section className="hero">
              <p className="eyebrow">Bible study library</p>

              <h1>Read and compare Bible versions</h1>

              <p>
                Explore Scripture across different translations
                using our Python API and React reader.
              </p>
            </section>

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

                    <button
                      type="button"
                      disabled={!version.available}
                      onClick={() =>
                        setSelectedVersion(version)
                      }
                    >
                      {version.available
                        ? "Open Bible"
                        : "Text not imported"}
                    </button>

                   {MEDIA_URL && version.pdf_filename && (

  <a
    className="pdf-button"
    href={`${MEDIA_URL}/${encodeURIComponent(
  version.pdf_filename
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
          </>
        )}
      </main>
    </div>
  );
}

export default App;
