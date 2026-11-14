import { fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";
import type { LabelData } from "../api/api";
import { LabelEditor, parseList, savedLook, withSavedLook } from "./LabelEditor";

const label: LabelData = {
  artist: "Jeff Mills", title: "The Bells", label: "Axis", catno: "AX-1", year: "1994", country: null,
  styles: ["Techno"], note: "A short note.", qr_url: "https://www.discogs.com/release/1", hidden: [],
  sizes: { artist: 1, details: 1, title: 1, info: 1, note: 1, tracks: 1 }, design: "glitchy",
  tracks: [
    { position: "A1", bpm: "135", key: "4A", tags: ["peak"], note: null, skip: false, hidden: [] },
    { position: "B1", bpm: null, key: null, tags: [], note: null, skip: false, hidden: [] },
  ],
};

function setup(value: LabelData = label) {
  const onChange = vi.fn();
  render(<LabelEditor value={value} onChange={onChange} />);
  return onChange;
}
const openCustomize = () => fireEvent.click(screen.getAllByRole("button", { name: /Customize/ }).at(-1)!);
const lastCall = (fn: ReturnType<typeof vi.fn>) => fn.mock.calls.at(-1)![0] as LabelData;

describe("LabelEditor", () => {
  it("edits a printed value", () => {
    const onChange = setup();
    fireEvent.change(screen.getByLabelText("Artist"), { target: { value: "Someone Else" } });
    expect(lastCall(onChange).artist).toBe("Someone Else");
  });

  it("lets you type a value the database does not have, and clears it back to nothing", () => {
    const onChange = setup();
    fireEvent.change(screen.getByLabelText("Country"), { target: { value: "UK" } });
    expect(lastCall(onChange).country).toBe("UK");
    fireEvent.change(screen.getByLabelText("Year"), { target: { value: "" } });
    expect(lastCall(onChange).year).toBeNull();
  });

  it("keeps Customize closed until it is opened", () => {
    setup();
    expect(screen.queryByLabelText("Print label")).toBeNull();
    openCustomize();
    expect(screen.getByLabelText("Print label")).toBeTruthy();
  });

  it("hides and shows a field in Customize, and a hidden field leaves the form", () => {
    localStorage.clear();
    const onChange = setup();
    openCustomize();
    fireEvent.click(screen.getByLabelText("Print label"));
    expect(lastCall(onChange).hidden).toEqual(["label"]);
    onChange.mockClear();
    render(<LabelEditor value={{ ...label, hidden: ["label", "year"] }} onChange={onChange} />);
    expect(screen.getAllByRole("textbox", { name: "Year" })).toHaveLength(1); // only the first editor still shows it
    openCustomize();
    fireEvent.click(screen.getAllByLabelText("Print year").at(-1)!);
    expect(lastCall(onChange).hidden).toEqual(["label"]);
    localStorage.clear();
  });

  it("hides a track field on every track and skips a track", () => {
    localStorage.clear();
    const onChange = setup();
    openCustomize();
    fireEvent.click(screen.getByLabelText("Print track bpm"));
    expect(lastCall(onChange).tracks!.map((t) => t.hidden)).toEqual([["bpm"], ["bpm"]]);
    localStorage.clear();
    fireEvent.click(screen.getByLabelText("Include track B1"));
    expect(lastCall(onChange).tracks![1].skip).toBe(true);
    expect(lastCall(onChange).tracks![0].skip).toBe(false);
  });

  it("edits one track's values without touching the others", () => {
    const onChange = setup();
    fireEvent.change(screen.getByLabelText("BPM B1"), { target: { value: "128" } });
    const tracks = lastCall(onChange).tracks!;
    expect(tracks[1].bpm).toBe("128");
    expect(tracks[0].bpm).toBe("135");
  });

  it("keeps a trailing comma while typing a list", () => {
    function Harness() {
      const [value, setValue] = useState(label);
      return <LabelEditor value={value} onChange={setValue} />;
    }
    render(<Harness />);
    const input = screen.getByLabelText("Styles") as HTMLInputElement;
    fireEvent.change(input, { target: { value: "Techno, " } });
    expect(input.value).toBe("Techno, ");
    fireEvent.change(input, { target: { value: "Techno, Dub Techno" } });
    expect(input.value).toBe("Techno, Dub Techno");
  });

  it("splits a list on commas and drops blanks", () => {
    expect(parseList(" a, ,b ,, c")).toEqual(["a", "b", "c"]);
  });

  it("offers a QR toggle only when there is a link to encode", () => {
    setup({ ...label, qr_url: null });
    openCustomize();
    expect(screen.queryByLabelText("Print qr code")).toBeNull();
  });

  it("remembers sizes and hidden fields for the next label", () => {
    localStorage.clear();
    function Harness() {
      const [value, setValue] = useState(label);
      return <LabelEditor value={value} onChange={setValue} />;
    }
    render(<Harness />);
    openCustomize();
    fireEvent.change(screen.getByLabelText("Note size"), { target: { value: "1.4" } });
    expect(savedLook().sizes.note).toBe(1.4);
    fireEvent.click(screen.getByLabelText("Print country"));
    fireEvent.click(screen.getByLabelText("Print track key"));
    const next = withSavedLook({ ...label, hidden: [] });
    expect(next.hidden).toEqual(["country"]);
    expect(next.tracks!.every((t) => (t.hidden ?? []).includes("key"))).toBe(true);
    localStorage.clear();
  });

  it("switches the design and keeps it for the next label", () => {
    localStorage.clear();
    const onChange = setup();
    openCustomize();
    fireEvent.click(screen.getByRole("button", { name: "Classic Penguin" }));
    expect(lastCall(onChange).design).toBe("penguin");
    expect(withSavedLook({ ...label }).design).toBe("penguin");
    localStorage.clear();
  });

  it("applies a preset, saves the current look under a name, and deletes one", () => {
    localStorage.clear();
    const save = vi.fn();
    const remove = vi.fn();
    const preset = { id: 7, name: "Shelf", look: { design: "factory" as const, sizes: { ...label.sizes, title: 1.3 }, hidden: ["country" as const], track_hidden: ["tags" as const] } };
    const onChange = vi.fn();
    render(<LabelEditor value={label} onChange={onChange} presets={{ items: [preset], save, remove }} />);
    openCustomize();
    fireEvent.click(screen.getByRole("button", { name: "Shelf" }));
    const applied = lastCall(onChange);
    expect([applied.design, applied.sizes.title, applied.hidden]).toEqual(["factory", 1.3, ["country"]]);
    expect(applied.tracks!.every((t) => t.hidden?.includes("tags"))).toBe(true);
    fireEvent.change(screen.getByLabelText("Preset name"), { target: { value: "Gig" } });
    fireEvent.click(screen.getByRole("button", { name: "Save preset" }));
    expect(save).toHaveBeenCalledWith("Gig", expect.objectContaining({ design: "glitchy" }));
    fireEvent.click(screen.getByLabelText("Delete preset Shelf"));
    expect(remove).toHaveBeenCalledWith(7);
    localStorage.clear();
  });
});

