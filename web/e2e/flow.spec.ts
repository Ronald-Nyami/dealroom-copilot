import { expect, test } from "@playwright/test";

test("question, cited answer, memo, challenger, review, approval, export, audit", async ({ page }) => {
  await page.goto("/");

  // A cited answer, with the source passage highlighted
  await page.getByTestId("question").fill("When does the Thun lease end?");
  await page.getByTestId("ask").click();
  await expect(page.getByTestId("answer")).toContainText("2033");
  await page.getByTestId("citation").first().click();
  await expect(page.getByTestId("highlight")).toContainText("30 June 2033");

  // An honest abstention
  await page.getByTestId("question").fill("What is the CEO's annual salary?");
  await page.getByTestId("ask").click();
  await expect(page.getByTestId("answer")).toHaveText("Not found in the data room.");

  // Analysts cannot draft the memo
  await page.getByRole("tab", { name: "IC memo" }).click();
  await page.getByTestId("draft-memo").click();
  await expect(page.getByTestId("memo-error")).toContainText("may not call draft_memo");

  // A partner drafts it; the challenger argues against the deal
  await page.getByTestId("role").selectOption("partner");
  await page.getByTestId("draft-memo").click();
  await expect(page.getByTestId("memo-state")).toHaveText("In review");
  const challenger = page.getByTestId("challenger");
  await expect(challenger).toContainText("does not match the audited accounts");
  await expect(challenger).toContainText("can terminate on change of control");
  await expect(challenger).toContainText("covenant headroom is thin");

  // Approval is refused until every high-severity argument has a response
  await page.getByTestId("approve").click();
  await expect(page.getByTestId("memo-error")).toContainText("respond to every high-severity challenger argument");
  const responses = page.getByTestId("response");
  for (let index = 0; index < (await responses.count()); index += 1) {
    await responses.nth(index).fill("Reviewed; addressed in the SPA conditions.");
  }
  await page.getByTestId("approve").click();
  await expect(page.getByTestId("memo-state")).toHaveText("Approved");

  // Export is a side effect: it needs an explicit approval first
  await page.getByTestId("export").click();
  await page.getByTestId("approve-export").click();
  await expect(page.getByTestId("exported")).toContainText("reports/ic_memo_");

  // Everything above is in a verified, hash-chained audit log
  await page.getByRole("tab", { name: "Audit" }).click();
  await expect(page.getByTestId("audit-verified")).toHaveText("Hash chain verified");
});
