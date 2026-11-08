import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { EngagementError, type EngagementApi } from "@/lib/engagement/client";

import { AssistantWidget, type AssistantLabels } from "./assistant-widget";

const labels: AssistantLabels = {
  button: "Open AI assistant",
  close: "Close AI assistant",
  title: "Bojro AI assistant",
  disclosureLabel: "AI assistant",
  start: "Start AI chat",
  starting: "Starting",
  firstMessage: "This is an AI assistant, not a person.",
  identityAnswer:
    "I am Bojro's AI assistant, not a person. I answer from verified Bojro product and policy information and can make mistakes.",
  inputLabel: "Message the AI assistant",
  placeholder: "Ask a question",
  send: "Send",
  sending: "Sending",
  sensitive: "Use the private order form.",
  tooLong: "Too long",
  genericError: "Could not answer",
  rateLimited: "Try again in {seconds} seconds.",
  retry: "Retry the same message",
  delete: "Delete this chat",
  deleting: "Deleting",
  deleted: "The chat was deleted.",
  citations: "Sources",
  handoff: "Continue on WhatsApp",
  uncertain: "Could not confirm.",
  verification: {
    open: "Check an order privately",
    title: "Private order check",
    description: "Structured form only.",
    number: "Order number",
    phone: "Delivery phone",
    submit: "Verify order",
    submitting: "Verifying",
    invalid: "Invalid fields",
    failure: "Could not match",
    result: "Redacted order status",
    status: "Order status",
    payment: "Payment status",
    area: "Delivery area",
    updated: "Latest update",
    statusRequest: "Show my verified order status.",
  },
};

describe("AssistantWidget", () => {
  it("discloses AI, blocks PII chat, verifies structurally, retries the same UUID, and deletes", async () => {
    const user = userEvent.setup();
    let resolveStatus!: (value: {
      message: {
        id: string;
        role: "assistant";
        content: string;
        citations: Array<{
          id: string;
          type: "order_status";
          label: string;
          href: null;
        }>;
        actions: [];
        grounded: true;
        created_at: string;
      };
      remaining_messages: number;
    }) => void;
    const statusResponse = new Promise<Parameters<typeof resolveStatus>[0]>((resolve) => {
      resolveStatus = resolve;
    });
    const sendAssistantMessage = vi
      .fn()
      .mockReturnValueOnce(statusResponse)
      .mockRejectedValueOnce(new EngagementError("network", { code: "NETWORK_ERROR" }))
      .mockResolvedValueOnce({
        message: {
          id: "assistant-2",
          role: "assistant",
          content: "The return policy is 7 days.",
          citations: [
            { id: "policy-1", type: "policy", label: "Return policy", href: "/en/return-refund" },
          ],
          actions: [],
          grounded: true,
          created_at: "2026-11-07T12:00:00Z",
        },
        remaining_messages: 8,
      });
    const api = {
      createAssistantSession: vi.fn().mockResolvedValue({
        id: "session-1",
        locale: "en",
        status: "active",
        assistant_name: "Bojro AI",
        disclosure: "I am an AI system.",
        disclosure_version: "v1",
        expires_at: "2026-11-08T12:00:00Z",
      }),
      sendAssistantMessage,
      verifyAssistantOrder: vi.fn().mockResolvedValue({
        verified: true,
        expires_at: "2026-11-07T12:10:00Z",
      }),
      deleteAssistantSession: vi.fn().mockResolvedValue(undefined),
    } as unknown as EngagementApi;

    render(
      <AssistantWidget
        api={api}
        labels={labels}
        locale="en"
        settings={{
          enabled: true,
          display_name: "Bojro AI",
          disclosure: "AI answers may be wrong.",
          disclosure_version: "v1",
        }}
        whatsapp={{ enabled: false, phone: "", message: "" }}
        whatsappLabel="WhatsApp"
      />,
    );
    await user.click(screen.getByRole("button", { name: "Open AI assistant" }));
    expect(screen.getByText("AI answers may be wrong.")).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Start AI chat" }));
    expect(await screen.findByText(/not a person/)).toBeVisible();
    expect(screen.getByRole("log", { name: "Bojro AI assistant" })).toBeVisible();

    const input = screen.getByLabelText("Message the AI assistant");
    await user.type(input, "Are you human?");
    await user.click(screen.getByRole("button", { name: "Send" }));
    expect(
      await screen.findByText(
        "I am Bojro's AI assistant, not a person. I answer from verified Bojro product and policy information and can make mistakes.",
      ),
    ).toBeVisible();
    expect(sendAssistantMessage).not.toHaveBeenCalled();

    await user.type(input, "My phone is 01712345678");
    await user.click(screen.getByRole("button", { name: "Send" }));
    expect(await screen.findByText("Use the private order form.")).toBeVisible();
    expect(sendAssistantMessage).not.toHaveBeenCalled();

    await user.type(screen.getByPlaceholderText("Order number"), "BJ-2026-000123");
    await user.type(screen.getByPlaceholderText("Delivery phone"), "01712345678");
    await user.click(screen.getByRole("button", { name: "Verify order" }));
    await waitFor(() => expect(sendAssistantMessage).toHaveBeenCalledTimes(1));
    expect(screen.queryByText("Redacted order status")).not.toBeInTheDocument();
    resolveStatus({
      message: {
        id: "assistant-status",
        role: "assistant",
        content: "The verified order is processing and paid.",
        citations: [
          {
            id: "order-status",
            type: "order_status",
            label: "Verified order status",
            href: null,
          },
        ],
        actions: [],
        grounded: true,
        created_at: "2026-11-07T12:00:00Z",
      },
      remaining_messages: 9,
    });
    expect(await screen.findByText(/verified order is processing/)).toBeVisible();
    expect(await screen.findByText("Redacted order status")).toBeVisible();
    expect(screen.queryByText("01712345678")).not.toBeInTheDocument();

    await user.clear(input);
    await user.type(input, "What is the return policy?");
    await user.click(screen.getByRole("button", { name: "Send" }));
    await user.click(await screen.findByRole("button", { name: "Retry the same message" }));
    expect(await screen.findByText("The return policy is 7 days.")).toBeVisible();
    expect(screen.getByRole("link", { name: "Return policy" })).toHaveAttribute(
      "href",
      "/en/return-refund",
    );
    expect(sendAssistantMessage).toHaveBeenCalledTimes(3);
    expect(sendAssistantMessage.mock.calls[1]?.[1].client_message_id).toBe(
      sendAssistantMessage.mock.calls[2]?.[1].client_message_id,
    );

    await user.click(screen.getByRole("button", { name: "Delete this chat" }));
    expect(await screen.findByText("The chat was deleted.")).toBeVisible();
  });
});
