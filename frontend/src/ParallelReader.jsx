import { useEffect, useRef, useState } from "react";
import HighlightedBibleText from "./HighlightedBibleText";

import {
  getBooks,
  getChapters,
  getParallel,
} from "./services/bibleApi";

const DEFAULT_PARALLEL_VERSIONS = [
  "KJV",
  "NIV",
  "BSB",
  "BBE",
];

function getDefaultVersions(versions) {
  const available = versions.map(
    (version) => version.abbreviation,
  );

  const [selectedAbbreviations, setSelectedAbbreviations] =
    useState(() => getDefaultVersions(versions));

  const remaining = available.filter(
    (abbreviation) => !preferred.includes(abbreviation),
  );

  return [...preferred, ...remaining].slice(0, 4);
}

function ParallelReader({ versions, onBack }) {
  const [books, setBooks] = useState([]);
  const [chapters, setChapters] = useState([]);

  const [selectedBook, setSelectedBook] = useState(1);
  const [selectedChapter, setSelectedChapter] = useState(1);

  const [parallelData, setParallelData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [selectedAbbreviations, setSelectedAbbreviations] =
  useState(() =>
    versions.map((version) => version.abbreviation)
  );

  const tableWrapperRef = useRef(null);

function scrollTable(direction) {
  tableWrapperRef.current?.scrollBy({
    left: direction * 600,
    behavior: "smooth",
  });
}


  useEffect(() => {
    async function initializeParallelReader() {
      setLoading(true);
      setError("");

      try {
         const abbreviations = selectedAbbreviations;

        const booksData = await getBooks(
          abbreviations[0],
        );

        const firstBook = booksData.books[0];

        const chaptersData = await getChapters(
          abbreviations[0],
          firstBook.position,
        );

        const firstChapter = chaptersData.chapters[0];

        const data = await getParallel(
          firstBook.position,
          firstChapter,
          abbreviations,
        );

        setBooks(booksData.books);
        setChapters(chaptersData.chapters);
        setSelectedBook(firstBook.position);
        setSelectedChapter(firstChapter);
        setParallelData(data);
      } catch (requestError) {
        setError(requestError.message);
      } finally {
        setLoading(false);
      }
    }

    initializeParallelReader();
  }, [selectedAbbreviations]);


  async function changeBook(
  bookPosition,
  useLastChapter = false,
) {
  setLoading(true);
  setError("");

  try {
    const abbreviations = selectedAbbreviations;

    const chaptersData = await getChapters(
      abbreviations[0],
      bookPosition,
    );

    const chapterNumber = useLastChapter
      ? chaptersData.chapters.at(-1)
      : chaptersData.chapters[0];

    const data = await getParallel(
      bookPosition,
      chapterNumber,
      abbreviations,
    );

    setSelectedBook(bookPosition);
    setSelectedChapter(chapterNumber);
    setChapters(chaptersData.chapters);
    setParallelData(data);

    window.scrollTo({ top: 0, behavior: "smooth" });
  } catch (requestError) {
    setError(requestError.message);
  } finally {
    setLoading(false);
  }
}

  async function changeChapter(chapterNumber) {
    setLoading(true);
    setError("");

    try {
      const abbreviations = selectedAbbreviations;

      const data = await getParallel(
        selectedBook,
        chapterNumber,
        abbreviations,
      );

      setSelectedChapter(chapterNumber);
      setParallelData(data);

      window.scrollTo({ top: 0, behavior: "smooth" });
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setLoading(false);
    }
  }

async function previousChapter() {
  const chapterIndex = chapters.indexOf(selectedChapter);

  if (chapterIndex > 0) {
    await changeChapter(chapters[chapterIndex - 1]);
    return;
  }

  const bookIndex = books.findIndex(
    (book) => book.position === selectedBook,
  );

  if (bookIndex > 0) {
    const previousBook = books[bookIndex - 1];

    await changeBook(previousBook.position, true);
  }
}


async function nextChapter() {
  const chapterIndex = chapters.indexOf(selectedChapter);

  if (chapterIndex < chapters.length - 1) {
    await changeChapter(chapters[chapterIndex + 1]);
    return;
  }

  const bookIndex = books.findIndex(
    (book) => book.position === selectedBook,
  );

  if (bookIndex < books.length - 1) {
    const nextBook = books[bookIndex + 1];

    await changeBook(nextBook.position);
  }
}

function toggleVersion(abbreviation) {
  setSelectedAbbreviations((current) => {
    if (current.includes(abbreviation)) {
      // Always keep at least one version selected.
      if (current.length === 1) {
        return current;
      }

      return current.filter(
        (item) => item !== abbreviation
      );
    }

    return [...current, abbreviation];
  });
}
  return (
    <section className="parallel-page">
      <button
        className="back-button"
        type="button"
        onClick={onBack}
      >
        ← Back to versions
      </button>

      <div className="parallel-toolbar">
      <fieldset className="parallel-version-picker">
  <legend>Versions</legend>

  <div className="parallel-version-options">
    {versions.map((version) => (
      <label key={version.id}>
        <input
          type="checkbox"
          checked={selectedAbbreviations.includes(
            version.abbreviation
          )}
          disabled={loading}
          onChange={() =>
            toggleVersion(version.abbreviation)
          }
        />

        <span>{version.abbreviation}</span>
      </label>
    ))}
  </div>
</fieldset>
        <label>
          Book
          <select
            value={selectedBook}
            disabled={loading}
            onChange={(event) =>
              changeBook(Number(event.target.value))
            }
          >
            {books.map((book) => (
              <option key={book.id} value={book.position}>
                {book.name}
              </option>
            ))}
          </select>
        </label>

        <label>
          Chapter
          <select
            value={selectedChapter}
            disabled={loading}
            onChange={(event) =>
              changeChapter(Number(event.target.value))
            }
          >
            {chapters.map((chapter) => (
              <option key={chapter} value={chapter}>
                {chapter}
              </option>
            ))}
          </select>
        </label>
      </div>

      {loading && (
        <p className="status">Loading comparison…</p>
      )}

      {error && (
        <p className="status error">{error}</p>
      )}

      {parallelData && (
        <article className="parallel-card">
          <header className="parallel-heading">
            <p>Parallel Bible</p>

            <h1>
              {parallelData.book.name}{" "}
              {parallelData.chapter}
            </h1>
          </header>

             <div className="table-scroll-controls">
  <button
    type="button"
    onClick={() => scrollTable(-1)}
  >
    ← Scroll Left
  </button>

  <button
    type="button"
    onClick={() => scrollTable(1)}
  >
    Scroll Right →
  </button>
</div>

          <div
  className="parallel-table-wrapper"
  ref={tableWrapperRef}
>
            <table className="parallel-table">
              <thead>
                <tr>
                  <th scope="col">Verse</th>

                  {parallelData.versions.map((version) => (
                    <th
                      scope="col"
                      key={version.id}
                    >
                      {version.abbreviation}
                    </th>
                  ))}
                </tr>
              </thead>
 <tbody>
  {parallelData.verses.map((verse) => (
    <tr key={verse.number}>
      <th scope="row">{verse.number}</th>

      {parallelData.versions.map((version) => (
        <td key={version.id}>
          {verse.texts[version.abbreviation] ? (
            <span
              className={
                verse.number === 1
                  ? "verse-text first-verse-text"
                  : "verse-text"
              }
            >
              <HighlightedBibleText
                text={
                  verse.texts[
                    version.abbreviation
                  ]
                }
              />
            </span>
          ) : (
            <span className="missing-text">
              —
            </span>
          )}
        </td>
      ))}
    </tr>
  ))}
</tbody>
            </table>
          </div>
<div className="chapter-navigation">
  <button
    type="button"
    disabled={
      loading ||
      (
        selectedBook === books[0]?.position &&
        selectedChapter === chapters[0]
      )
    }
    onClick={previousChapter}
  >
    ← Previous Chapter
  </button>

  <button
    type="button"
    disabled={
      loading ||
      (
        selectedBook === books.at(-1)?.position &&
        selectedChapter === chapters.at(-1)
      )
    }
    onClick={nextChapter}
  >
    Next Chapter →
  </button>
</div>
        </article>
      )}
    </section>
  );
}

export default ParallelReader;
