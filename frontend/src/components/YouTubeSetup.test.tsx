import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { YouTubeCredentialsForm, YouTubeQuota, YouTubeSetupGuide } from "./YouTubeSetup";

const save = vi.fn();
vi.mock("../api/api", () => ({ api: { saveYouTubeCredentials: (...a: unknown[]) => save(...a) } }));
vi.mock("../toast", () => ({ pushToast: vi.fn() }));

const wrap = (ui: React.ReactNode) =>
  render(<QueryClientProvider client={new QueryClient({ defaultOptions: { mutations: { retry: false } } })}>{ui}</QueryClientProvider>);

beforeEach(() => save.mockReset());

describe("YouTube setup", () => {
  it("links every step to its Google Cloud page", () => {
    render(<YouTubeSetupGuide />);
    const links = screen.getAllByRole("link", { name: /Open/ });
    expect(links).toHaveLength(5);
    expect(links[1]).toHaveAttribute("href", "https://console.cloud.google.com/apis/library/youtube.googleapis.com");
    links.forEach((a) => expect(a).toHaveAttribute("target", "_blank"));
  });

  it("saves the pasted ID and secret, and shows Google's refusal", async () => {
    save.mockRejectedValueOnce(new Error("Google does not know this client ID and secret"));
    const done = vi.fn();
    wrap(<YouTubeCredentialsForm onDone={done} />);
    const button = screen.getByRole("button", { name: "Save and check" });
    expect(button).toBeDisabled();
    fireEvent.change(screen.getByLabelText("Client ID"), { target: { value: "1-a.apps.googleusercontent.com" } });
    fireEvent.change(screen.getByLabelText("Client secret"), { target: { value: "wrong" } });
    fireEvent.click(button);
    expect(await screen.findByRole("alert")).toHaveTextContent("Google does not know");
    expect(done).not.toHaveBeenCalled();

    save.mockResolvedValueOnce({ checked: true });
    fireEvent.click(button);
    await waitFor(() => expect(done).toHaveBeenCalled());
    expect(save).toHaveBeenLastCalledWith("1-a.apps.googleusercontent.com", "wrong");
  });

  it("shows units used, tracks left and turns red near the limit", () => {
    const { rerender } = render(<YouTubeQuota usage={{ used: 1250, limit: 10000, resets_at: "2026-11-04T08:00:00Z" }} />);
    expect(screen.getByTestId("youtube-quota")).toHaveTextContent("about 175 tracks left");
    expect(screen.getByRole("meter")).toHaveAttribute("aria-valuenow", "1250");
    rerender(<YouTubeQuota usage={{ used: 10000, limit: 10000, resets_at: "2026-11-04T08:00:00Z" }} />);
    expect(screen.getByTestId("youtube-quota")).toHaveTextContent("used up");
  });
});
