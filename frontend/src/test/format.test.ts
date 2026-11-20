import { checkFile, escapeRegExp, formatBytes, formatDuration, formatMoney, formatPercent, issueLabel } from "../lib/format";

const file = (name: string, size = 100) => new File([new Uint8Array(size)], name);

describe("format helpers", () => {
  it("formats bytes", () => {
    expect(formatBytes(512)).toBe("512 B");
    expect(formatBytes(2048)).toBe("2.0 KB");
    expect(formatBytes(5 * 1024 * 1024)).toBe("5.0 MB");
    expect(formatBytes(-1)).toBe("-");
  });
  it("formats money", () => {
    expect(formatMoney("1234.5", "usd")).toBe("USD 1,234.50");
    expect(formatMoney(null)).toBe("-");
    expect(formatMoney("abc")).toBe("abc");
  });
  it("formats durations and percentages", () => {
    expect(formatDuration(450)).toBe("450 ms");
    expect(formatDuration(2500)).toBe("2.5 s");
    expect(formatDuration(125000)).toBe("2 min 5 s");
    expect(formatPercent(0.954)).toBe("95%");
    expect(formatPercent(null)).toBe("-");
  });
  it("validates files before upload", () => {
    expect(checkFile(file("a.pdf"))).toBeNull();
    expect(checkFile(file("SCAN.TIFF"))).toBeNull();
    expect(checkFile(file("notes.docx"))).toMatch(/Unsupported/);
    expect(checkFile(file("empty.pdf", 0))).toMatch(/empty/i);
    const big = new File([""], "big.pdf");
    Object.defineProperty(big, "size", { value: 60 * 1024 * 1024 });
    expect(checkFile(big)).toMatch(/Larger/);
  });
  it("escapes regex characters", () => {
    expect(new RegExp(escapeRegExp("a.b*(c)")).test("a.b*(c)")).toBe(true);
    expect(new RegExp(escapeRegExp("a.b")).test("axb")).toBe(false);
  });
  it("labels issue codes", () => {
    expect(issueLabel("TOTAL_MISMATCH")).toBe("Total mismatch");
    expect(issueLabel("SOMETHING_NEW")).toBe("Something new");
  });
});
