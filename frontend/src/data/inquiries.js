// The four canned inquiries sent to the real backend (/api/synthesize).
// Query text is scoped to the columns that actually exist in the working
// dataset: bigquery-public-data.thelook_ecommerce.order_items, filtered to
// non-cancelled/non-returned rows —
//   id, order_id, user_id, product_id, sale_price, created_at, status

export const INQUIRIES = [
  {
    label: 'High-Value Order Classification',
    query:
      'Train a classifier to predict whether an order is high-value (top quartile by sale_price) using features derived from order timing and product_id, and return the top 20 highest-probability orders with pred_prob.',
    taskType: 'classification',
  },
  {
    label: 'Product Revenue Alerting',
    query:
      "Compute a 7-day rolling average daily revenue per product. Flag the top 10 products where today's revenue is more than 30% above the rolling average.",
    taskType: 'rolling_window',
  },
  {
    label: 'Order Aging Triage',
    query:
      'Rank the top 25 orders still in Processing status by priority, using order age (time since created_at) and sale_price.',
    taskType: 'ranking',
  },
  {
    label: 'Executive Summary',
    query:
      'Create a dashboard summary grouped by status and price tier (bucket sale_price into Low, Mid, and High) showing total revenue, order count, and avg order value.',
    taskType: 'groupby_aggregation',
  },
]
