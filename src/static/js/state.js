const State = {
  workflows: {},
  runs: [],
  selectedWorkflowId: null,
  selectedRunId: null,
  pollTimer: null,
  highlightedNodeId: null,
  lastDAGArgs: { wf: null, trace: null },
  statsVisible: false,
};

const EXAMPLES = {
  order_fulfillment: {
    id: "order-fulfillment",
    name: "Order Fulfillment",
    version: 1,
    start_node_id: "check_inventory",
    nodes: {
      check_inventory: {
        id: "check_inventory",
        type: "third_party",
        label: "Check Inventory",
        config: {
          url: "https://httpbin.org/post",
          method: "POST",
          body: { sku: "{{context.sku}}" },
          retry: { max_attempts: 3, backoff_ms: 500 },
          mock: { status: 200, body: { in_stock: true } }
        },
        next: "branch_in_stock"
      },
      branch_in_stock: {
        id: "branch_in_stock",
        type: "branch",
        label: "In Stock?",
        edges: [
          {
            label: "yes",
            condition: { field: "nodes.check_inventory.response.in_stock", operator: "equals", value: true },
            next: "create_shipment"
          },
          {
            label: "no",
            condition: { field: "nodes.check_inventory.response.in_stock", operator: "equals", value: false },
            next: "end_cancelled"
          }
        ]
      },
      create_shipment: {
        id: "create_shipment",
        type: "third_party",
        label: "Create Shipment",
        config: {
          url: "https://httpbin.org/post",
          method: "POST",
          mock: { status: 200, body: { shipment_id: "SHP-123" } }
        },
        next: "end_success"
      },
      end_success: { id: "end_success", type: "end", label: "Order Fulfilled" },
      end_cancelled: { id: "end_cancelled", type: "end", label: "Cancelled" }
    }
  },

  email_validation: {
    id: "email-validation",
    name: "Email Validation Pipeline",
    version: 1,
    start_node_id: "validate_email",
    nodes: {
      validate_email: {
        id: "validate_email",
        type: "third_party",
        label: "Validate Email",
        config: {
          url: "https://httpbin.org/post",
          method: "POST",
          body: { email: "{{context.email}}" },
          retry: { max_attempts: 2, backoff_ms: 500 },
          mock: { status: 200, body: { valid: true } }
        },
        next: "email_valid"
      },
      email_valid: {
        id: "email_valid",
        type: "branch",
        label: "Email Valid?",
        edges: [
          {
            label: "yes",
            condition: { field: "nodes.validate_email.response.valid", operator: "equals", value: true },
            next: "check_ip"
          },
          {
            label: "no",
            condition: { field: "nodes.validate_email.response.valid", operator: "equals", value: false },
            next: "end_rejected"
          }
        ]
      },
      check_ip: {
        id: "check_ip",
        type: "third_party",
        label: "Check IP Risk",
        config: {
          url: "https://httpbin.org/post",
          method: "POST",
          body: { ip: "{{context.ip}}" },
          retry: { max_attempts: 2, backoff_ms: 500 },
          mock: { status: 200, body: { risk_score: "low" } }
        },
        next: "risk_level"
      },
      risk_level: {
        id: "risk_level",
        type: "branch",
        label: "Risk Level?",
        edges: [
          {
            label: "low",
            condition: { field: "nodes.check_ip.response.risk_score", operator: "equals", value: "low" },
            next: "send_welcome"
          },
          {
            label: "medium",
            condition: { field: "nodes.check_ip.response.risk_score", operator: "equals", value: "medium" },
            next: "trigger_sms"
          },
          {
            label: "high",
            condition: { field: "nodes.check_ip.response.risk_score", operator: "equals", value: "high" },
            next: "log_security"
          }
        ]
      },
      send_welcome: {
        id: "send_welcome",
        type: "third_party",
        label: "Send Welcome Email",
        config: {
          url: "https://httpbin.org/post",
          method: "POST",
          body: { to: "{{context.email}}", template: "welcome" },
          mock: { status: 200, body: { sent: true } }
        },
        next: "end_success"
      },
      trigger_sms: {
        id: "trigger_sms",
        type: "third_party",
        label: "Trigger SMS Verification",
        config: {
          url: "https://httpbin.org/post",
          method: "POST",
          body: { phone: "{{context.phone}}" },
          mock: { status: 200, body: { sms_sent: true } }
        },
        next: "end_pending"
      },
      log_security: {
        id: "log_security",
        type: "third_party",
        label: "Log Security Event",
        config: {
          url: "https://httpbin.org/post",
          method: "POST",
          body: { event: "high_risk_signup", email: "{{context.email}}" },
          mock: { status: 200, body: { logged: true } }
        },
        next: "end_blocked"
      },
      end_success: { id: "end_success", type: "end", label: "Signup Successful" },
      end_pending: { id: "end_pending", type: "end", label: "Pending SMS Verification" },
      end_blocked: { id: "end_blocked", type: "end", label: "Blocked \u2014 High Risk" },
      end_rejected: { id: "end_rejected", type: "end", label: "Rejected \u2014 Invalid Email" }
    }
  },

  user_lookup: {
    id: "user-lookup",
    name: "User Lookup Pipeline",
    version: 1,
    start_node_id: "fetch_user",
    nodes: {
      fetch_user: {
        id: "fetch_user",
        type: "third_party",
        label: "Fetch User",
        config: {
          url: "https://jsonplaceholder.typicode.com/users/{{context.user_id}}",
          method: "GET",
          timeout_ms: 10000,
          retry: { max_attempts: 2, backoff_ms: 1000 },
          mock: {
            status: 200,
            body: { id: 1, name: "Leanne Graham", company: { name: "Romaguera-Crona" } }
          }
        },
        next: "fetch_posts"
      },
      fetch_posts: {
        id: "fetch_posts",
        type: "third_party",
        label: "Fetch User Posts",
        config: {
          url: "https://jsonplaceholder.typicode.com/posts?userId={{context.user_id}}",
          method: "GET",
          timeout_ms: 10000,
          retry: { max_attempts: 2, backoff_ms: 1000 },
          mock: {
            status: 200,
            body: [{ id: 1, title: "Post 1" }, { id: 2, title: "Post 2" }]
          }
        },
        next: "check_activity"
      },
      check_activity: {
        id: "check_activity",
        type: "branch",
        label: "Active User?",
        edges: [
          {
            label: "active",
            condition: { field: "nodes.fetch_posts.response.0.id", operator: "exists" },
            next: "end_active"
          }
        ],
        default_next: "end_inactive"
      },
      end_active: { id: "end_active", type: "end", label: "Active User" },
      end_inactive: { id: "end_inactive", type: "end", label: "Inactive User" }
    }
  },

  fault_tolerance: {
    id: "fault-tolerance-test",
    name: "Fault Tolerance Test",
    version: 1,
    start_node_id: "flaky_call",
    nodes: {
      flaky_call: {
        id: "flaky_call",
        type: "third_party",
        label: "Flaky API (fails 2x, then OK)",
        config: {
          url: "http://localhost:8000/test/flaky?fail_count=2",
          method: "GET",
          timeout_ms: 5000,
          retry: { max_attempts: 3, backoff_ms: 500 },
          mock: { status: 200, body: { status: "ok", message: "Recovered after retries" } }
        },
        next: "check_result"
      },
      check_result: {
        id: "check_result",
        type: "branch",
        label: "Success?",
        edges: [
          {
            label: "recovered",
            condition: { field: "nodes.flaky_call.response.status", operator: "equals", value: "ok" },
            next: "end_ok"
          }
        ],
        default_next: "end_fail"
      },
      end_ok: { id: "end_ok", type: "end", label: "Recovered!" },
      end_fail: { id: "end_fail", type: "end", label: "Failed After Retries" }
    }
  },

  resume_test: {
    id: "resume-test",
    name: "Resume Test Pipeline",
    version: 1,
    start_node_id: "fetch_user",
    nodes: {
      fetch_user: {
        id: "fetch_user",
        type: "third_party",
        label: "Fetch User",
        config: {
          url: "https://jsonplaceholder.typicode.com/users/{{context.user_id}}",
          method: "GET",
          timeout_ms: 10000,
          retry: { max_attempts: 2, backoff_ms: 1000 },
          mock: {
            status: 200,
            body: { id: 1, name: "Leanne Graham", email: "leanne@example.com" }
          }
        },
        next: "enrich_profile"
      },
      enrich_profile: {
        id: "enrich_profile",
        type: "third_party",
        label: "Enrich Profile (Flaky)",
        config: {
          url: "http://localhost:8000/test/flaky?fail_count=1",
          method: "GET",
          timeout_ms: 5000,
          retry: { max_attempts: 1, backoff_ms: 0 },
          mock: { status: 200, body: { risk_score: 12, tier: "premium" } }
        },
        next: "check_tier"
      },
      check_tier: {
        id: "check_tier",
        type: "branch",
        label: "Premium User?",
        edges: [
          {
            label: "premium",
            condition: { field: "nodes.enrich_profile.response.tier", operator: "equals", value: "premium" },
            next: "fetch_rewards"
          }
        ],
        default_next: "end_basic"
      },
      fetch_rewards: {
        id: "fetch_rewards",
        type: "third_party",
        label: "Fetch Rewards",
        config: {
          url: "https://jsonplaceholder.typicode.com/posts?userId={{context.user_id}}",
          method: "GET",
          timeout_ms: 10000,
          retry: { max_attempts: 2, backoff_ms: 1000 },
          mock: {
            status: 200,
            body: [{ id: 1, reward: "10% discount" }, { id: 2, reward: "Free shipping" }]
          }
        },
        next: "end_premium"
      },
      end_premium: { id: "end_premium", type: "end", label: "Premium Complete" },
      end_basic: { id: "end_basic", type: "end", label: "Basic Complete" }
    }
  }
};
