import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { axe } from "vitest-axe";
import { AppShell } from "../components/AppShell";
import { StatusBadge } from "../components/StatusBadge";
import { mockClient } from "../test/fixtures";
import { renderWithApi } from "../test/render";
import { ClaimBoard } from "./ClaimBoard";

async function renderBoard(opts: Parameters<typeof mockClient>[0] = {}) {
  const utils = renderWithApi(
    <AppShell>
      <ClaimBoard />
    </AppShell>,
    mockClient(opts),
  );
  return utils;
}

const table = () => screen.getByRole("table", { name: "Claims" });
const bodyRows = () => within(table()).getAllByRole("row").slice(1);

describe("ClaimBoard", () => {
  it("renders the headline, the ruler counts and one row per claim in attention order", async () => {
    await renderBoard();
    await screen.findByRole("table", { name: "Claims" });
    // 3 of 5 are not accepted (violated, stale, inconclusive); baseline is the previous snapshot's git rev.
    expect(screen.getByText(/claims need/)).toHaveTextContent("3 of 5 claims need revalidation since a1b2c3d");
    const ruler = screen.getByRole("region", { name: "Claims by status" });
    expect(within(ruler).getByRole("button", { name: /Violated 1 20%/ })).toBeInTheDocument();
    const ids = bodyRows().map((r) => within(r).getAllByRole("cell")[0]?.textContent);
    expect(ids).toEqual(["C-P01-PM", "C-P02-PM", "C-P02-SW", "C-P03-IS", "C-P01-SW"]);
  });

  it("shows every status as an icon plus a text label, never colour alone", async () => {
    await renderBoard();
    await screen.findByRole("table", { name: "Claims" });
    await screen.findAllByRole("img", { name: "Supported" });
    const first = bodyRows()[0];
    expect(first).toBeDefined();
    const chip = within(first as HTMLElement).getByText("Violated").closest(".st-chip");
    expect(chip?.querySelector("svg")).not.toBeNull();
    // compact history glyphs carry an accessible name instead of visible text
    expect((await within(first as HTMLElement).findAllByRole("img", { name: "Supported" })).length).toBeGreaterThan(0);
  });

  it("joins requirement, limit and criticality from the snapshot", async () => {
    await renderBoard();
    await screen.findByRole("table", { name: "Claims" });
    const row = bodyRows()[0] as HTMLElement;
    expect(row).toHaveTextContent("R-PM-MAX");
    expect(row).toHaveTextContent("≤ 90 °C");
    expect(row).toHaveTextContent("High");
    expect(row).toHaveTextContent("Requirement violated");
  });

  it("filters by status, requirement, criticality and text", async () => {
    const user = userEvent.setup();
    await renderBoard();
    await screen.findByRole("table", { name: "Claims" });

    await user.click(screen.getByRole("button", { name: /Stale 1/ }));
    expect(bodyRows()).toHaveLength(1);
    expect(screen.getByRole("button", { name: /Stale 1/ })).toHaveAttribute("aria-pressed", "true");
    await user.click(screen.getByRole("button", { name: /Clear filters/ }));
    expect(bodyRows()).toHaveLength(5);

    await user.selectOptions(screen.getByRole("combobox", { name: "Requirement" }), "R-SW-MAX");
    expect(bodyRows()).toHaveLength(2);
    await user.selectOptions(screen.getByRole("combobox", { name: "Requirement" }), "");

    await user.selectOptions(screen.getByRole("combobox", { name: "Criticality" }), "low");
    expect(bodyRows()).toHaveLength(1);
    await user.selectOptions(screen.getByRole("combobox", { name: "Criticality" }), "");

    await user.type(screen.getByRole("searchbox", { name: "Search claims" }), "freshness");
    expect(bodyRows()).toHaveLength(1);
    await user.clear(screen.getByRole("searchbox", { name: "Search claims" }));
    await user.type(screen.getByRole("searchbox", { name: "Search claims" }), "nothing-matches");
    expect(screen.getByText("No claims match these filters")).toBeInTheDocument();
  });

  it("sorts by a column header and reports aria-sort", async () => {
    const user = userEvent.setup();
    await renderBoard();
    await screen.findByRole("table", { name: "Claims" });
    await user.click(screen.getByRole("button", { name: "Claim" }));
    expect(screen.getByRole("columnheader", { name: "Claim" })).toHaveAttribute("aria-sort", "ascending");
    expect(within(bodyRows()[0] as HTMLElement).getAllByRole("cell")[0]).toHaveTextContent("C-P01-PM");
    await user.click(screen.getByRole("button", { name: "Claim" }));
    expect(within(bodyRows()[0] as HTMLElement).getAllByRole("cell")[0]).toHaveTextContent("C-P03-IS");
  });

  it("opens the detail drawer from the keyboard and closes it with Escape", async () => {
    const user = userEvent.setup();
    await renderBoard();
    await screen.findByRole("table", { name: "Claims" });
    const rows = bodyRows();
    (rows[0] as HTMLElement).focus();
    await user.keyboard("{ArrowDown}");
    expect(rows[1]).toHaveFocus();
    await user.keyboard("{Enter}");
    const drawer = await screen.findByRole("dialog", { name: "C-P02-PM" });
    expect(within(drawer).getByText("evidence_invalidated")).toBeInTheDocument();
    expect(within(drawer).getByRole("button", { name: "Close claim detail" })).toHaveFocus();
    await user.keyboard("{Escape}");
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });

  it("shows an error state with a retry when the API fails", async () => {
    await renderBoard({ failClaims: true });
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Could not load claims");
    expect(alert).toHaveTextContent("unknown snapshot 'zzz'");
    expect(within(alert).getByRole("button", { name: /Try again/ })).toBeInTheDocument();
  });

  it("shows an empty state when the project declares no claims", async () => {
    await renderBoard({ claims: [] });
    expect(await screen.findByText("No claims declared")).toBeInTheDocument();
  });

  it("has no axe violations, with and without the drawer open", async () => {
    const user = userEvent.setup();
    const { container } = await renderBoard();
    await screen.findByRole("table", { name: "Claims" });
    await waitFor(() => expect(screen.getAllByRole("img", { name: "Supported" }).length).toBeGreaterThan(0));
    expect((await axe(container)).violations).toEqual([]);
    await user.click(bodyRows()[0] as HTMLElement);
    await screen.findByRole("dialog");
    expect((await axe(container)).violations).toEqual([]);
  });
});

describe("StatusBadge", () => {
  it("renders the label next to the icon", () => {
    renderWithApi(<StatusBadge status="inconclusive" />, mockClient());
    expect(screen.getByText("Inconclusive")).toBeInTheDocument();
  });
});
