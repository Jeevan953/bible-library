const API_URL = (
  import.meta.env.VITE_API_URL ||
  "http://127.0.0.1:8000/api"
).replace(/\/+$/, "");

async function request(path) {
  const response = await fetch(`${API_URL}${path}`);

  if (!response.ok) {
    let message = `API returned ${response.status}`;

    try {
      const data = await response.json();
      message = data.detail || message;
    } catch {
      // Keep the original error message.
    }

    throw new Error(message);
  }

  return response.json();
}

export function getVersions() {
  return request("/versions/");
}

export function getBooks(abbreviation) {
  return request(`/versions/${abbreviation}/books/`);
}

export function getChapters(abbreviation, bookPosition) {
  return request(
    `/versions/${abbreviation}/books/${bookPosition}/chapters/`,
  );
}

export function getChapter(
  abbreviation,
  bookPosition,
  chapterNumber,
) {
  return request(
    `/read/${abbreviation}/${bookPosition}/${chapterNumber}/`,
  );
}

export function getParallel(
  bookPosition,
  chapterNumber,
  abbreviations,
) {
  const versions = encodeURIComponent(
    abbreviations.join(","),
  );

  return request(
    `/parallel/${bookPosition}/${chapterNumber}/` +
      `?versions=${versions}`,
  );
}

export function searchBible(
  abbreviation,
  query,
  page = 1,
) {
  const parameters = new URLSearchParams({
    version: abbreviation,
    q: query,
    page: String(page),
  });

  return request(
    `/search/?${parameters.toString()}`,
  );
}
