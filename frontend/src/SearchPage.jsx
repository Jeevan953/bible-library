import { useState } from "react";
import HighlightedBibleText from "./HighlightedBibleText";

import { searchBible } from "./services/bibleApi";


function SearchPage({
  versions,
  onOpenResult,
  onBack,
}) {
  const defaultVersion =
    versions.find(
      (version) => version.abbreviation === "KJV",
    ) || versions[0];

  const [selectedVersion, setSelectedVersion] = useState(
    defaultVersion?.abbreviation || "",
  );

  const [query, setQuery] = useState("");
  const [searchData, setSearchData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");


  async function performSearch(page = 1) {
    const cleanQuery = query.trim();

    if (!cleanQuery) {
      setError("Enter a word or phrase to search.");
      return;
    }

    setLoading(true);
    setError("");

    try {
      const data = await searchBible(
        selectedVersion,
        cleanQuery,
        page,
      );

      setSearchData(data);

      window.scrollTo({
        top: 0,
        behavior: "smooth",
      });
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setLoading(false);
    }
  }


  function handleSubmit(event) {
    event.preventDefault();
    performSearch(1);
  }


  return (
    <section className="search-page">
      <button
        className="back-button"
        type="button"
        onClick={onBack}
      >
        ← Back to versions
      </button>

      <div className="search-panel">
        <header className="search-heading">
          <p>Bible Search</p>
          <h1>Search Scripture</h1>
        </header>

        <form
          className="search-form"
          onSubmit={handleSubmit}
        >
          <label>
            Version
            <select
              value={selectedVersion}
              disabled={loading}
              onChange={(event) => {
                setSelectedVersion(event.target.value);
                setSearchData(null);
              }}
            >
              {versions.map((version) => (
                <option
                  key={version.id}
                  value={version.abbreviation}
                >
                  {version.abbreviation}
                </option>
              ))}
            </select>
          </label>

          <label className="search-query-label">
            Word or phrase
            <input
              type="search"
              value={query}
              placeholder="Example: in the beginning"
              disabled={loading}
              onChange={(event) =>
                setQuery(event.target.value)
              }
            />
          </label>

          <button
            className="search-button"
            type="submit"
            disabled={loading}
          >
            {loading ? "Searching…" : "Search"}
          </button>
        </form>
      </div>

      {error && (
        <p className="status error">{error}</p>
      )}

      {searchData && (
        <div className="search-results">
          <div className="search-summary">
            <h2>
              Results for “{searchData.query}”
            </h2>

            <span>
              {searchData.count} matches in{" "}
              {searchData.version.abbreviation}
            </span>
          </div>

          {searchData.results.length === 0 ? (
            <p className="status">
              No matching verses were found.
            </p>
          ) : (
            <div className="result-list">
              {searchData.results.map((result) => (
                <article
                  className="search-result"
                  key={result.reference}
                >
                  <button
  className="search-result-link"
  type="button"
  onClick={() =>
    onOpenResult(selectedVersion, result)
  }
>
  {result.reference}
</button>
                  <p>
  <HighlightedBibleText text={result.text} />
</p>
                </article>
              ))}
            </div>
          )}

          {searchData.total_pages > 1 && (
            <div className="search-pagination">
              <button
                type="button"
                disabled={
                  loading || searchData.page <= 1
                }
                onClick={() =>
                  performSearch(searchData.page - 1)
                }
              >
                ← Previous
              </button>

              <span>
                Page {searchData.page} of{" "}
                {searchData.total_pages}
              </span>

              <button
                type="button"
                disabled={
                  loading ||
                  searchData.page >=
                    searchData.total_pages
                }
                onClick={() =>
                  performSearch(searchData.page + 1)
                }
              >
                Next →
              </button>
            </div>
          )}
        </div>
      )}
    </section>
  );
}

export default SearchPage;
