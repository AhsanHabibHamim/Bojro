import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { AccountError, type AccountApi } from "@/lib/account/client";
import type { SupportMessage } from "@/lib/account/types";
import { renderWithAccount } from "@/test/render-account";

import { mergeChronological, TicketThread } from "./ticket-thread";

const messages: SupportMessage[] = [
  {
    id: "message-2",
    body: "Second",
    author_type: "admin",
    author_name: "Bojro support",
    created_at: "2026-11-07T10:02:00Z",
  },
  {
    id: "message-1",
    body: "First",
    author_type: "customer",
    author_name: "Asha",
    created_at: "2026-11-07T10:01:00Z",
  },
];

describe("support ticket thread", () => {
  it("deduplicates replayed messages and preserves chronological ordering", () => {
    const replay = { ...messages[0]!, body: "Second (replayed response)" };
    expect(mergeChronological(messages, replay).map((item) => [item.id, item.body])).toEqual([
      ["message-1", "First"],
      ["message-2", "Second (replayed response)"],
    ]);
  });

  it("reuses the compose idempotency key after an ambiguous network result", async () => {
    const ticket = {
      data: {
        number: "SUP-2026-000001",
        subject: "Delivery question",
        status: "open" as const,
        order_number: "BJ-2026-000001",
        last_message_at: "2026-11-07T10:02:00Z",
        unread_count: 0,
        created_at: "2026-11-07T10:00:00Z",
        updated_at: "2026-11-07T10:02:00Z",
        revision: 1,
      },
      etag: '"ticket:1"',
    };
    const sendTicketMessage = vi
      .fn()
      .mockRejectedValueOnce(new AccountError("offline", { code: "NETWORK_ERROR" }))
      .mockResolvedValueOnce({
        id: "message-3",
        body: "Please share an update",
        author_type: "customer",
        author_name: "Asha",
        created_at: "2026-11-07T10:03:00Z",
      });
    const accountApi = {
      ticket: vi
        .fn()
        .mockResolvedValueOnce(ticket)
        .mockResolvedValue({
          data: { ...ticket.data, revision: 2 },
          etag: '"ticket:2"',
        }),
      ticketMessages: vi.fn().mockResolvedValue({ items: messages, next_cursor: null }),
      markTicketRead: vi.fn().mockResolvedValue(undefined),
      sendTicketMessage,
      closeTicket: vi.fn().mockResolvedValue({
        data: { ...ticket.data, status: "closed", revision: 3 },
        etag: '"ticket:3"',
      }),
    } as unknown as AccountApi;
    const user = userEvent.setup();
    renderWithAccount(<TicketThread locale="en" number="SUP-2026-000001" />, { accountApi });

    const input = await screen.findByLabelText("Write a reply");
    await user.type(input, "Please share an update");
    await user.click(screen.getByRole("button", { name: "Send reply" }));
    await screen.findByRole("alert");
    await user.click(screen.getByRole("button", { name: "Send reply" }));
    await waitFor(() => expect(sendTicketMessage).toHaveBeenCalledTimes(2));

    const firstKey = sendTicketMessage.mock.calls[0]![2];
    const retryKey = sendTicketMessage.mock.calls[1]![2];
    expect(firstKey).toBe(retryKey);
    expect(await screen.findByText("Please share an update")).toBeVisible();
    await waitFor(() => expect(accountApi.ticket).toHaveBeenCalledTimes(2));
    await user.click(screen.getByRole("button", { name: "Close ticket" }));
    expect(accountApi.closeTicket).toHaveBeenCalledWith("SUP-2026-000001", '"ticket:2"');
  });
});
