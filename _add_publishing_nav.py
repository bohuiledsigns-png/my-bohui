"""Add publishing pages to role-based access in the CRM sidebar."""
with open('templates/index.html', 'r', encoding='utf-8') as f:
    content = f.read()

indent = "              "  # 14 spaces

# Add to admin role pages
admin_old = "admin: ['dashboard','customers','leads','lead-followup','chat','media','products',\n" + indent + "'calc','quotes','orders','order-stats','lead-analytics','ar-dashboard',\n" + indent + "'commission','production','inventory','partners','purchase-orders',\n" + indent + "'catalog','email','ai','prompts','knowledge','scripts','countries',\n" + indent + "'cases-admin','qc-templates','users','reports','activity-logs',\n" + indent + "'v5-regions','v5-agents','v5-factories','v5-pricing','v5-leads','v5-dashboard','v6-pl','v6-invoices','v6-expenses','v6-budgets','v6-cashflow','v6-exec'"

admin_new = "admin: ['dashboard','customers','leads','lead-followup','chat','media','products',\n" + indent + "'calc','quotes','orders','order-stats','lead-analytics','ar-dashboard',\n" + indent + "'commission','production','inventory','partners','purchase-orders',\n" + indent + "'catalog','email','ai','prompts','knowledge','scripts','countries',\n" + indent + "'cases-admin','qc-templates','users','reports','activity-logs',\n" + indent + "'v5-regions','v5-agents','v5-factories','v5-pricing','v5-leads','v5-dashboard','v6-pl','v6-invoices','v6-expenses','v6-budgets','v6-cashflow','v6-exec',\n" + indent + "'pub-dashboard','pub-accounts','pub-schedule','pub-content','pub-analytics','pub-comments','pub-reports'"

if admin_old in content:
    content = content.replace(admin_old, admin_new)
    print("Admin pages updated")
else:
    print("Admin pages NOT FOUND")

# Add to sales role pages
sales_old = "sales: ['dashboard','customers','leads','lead-followup','chat','media','products',\n" + indent + "'calc','quotes','orders','order-stats','lead-analytics','ar-dashboard',\n" + indent + "'commission','production','inventory','partners','purchase-orders',\n" + indent + "'catalog','email','ai','prompts','knowledge','scripts','countries',\n" + indent + "'reports','activity-logs',\n" + indent + "'v5-regions','v5-agents','v5-factories','v5-pricing','v5-leads','v5-dashboard','v6-pl','v6-invoices','v6-expenses','v6-budgets','v6-cashflow','v6-exec'"

sales_new = "sales: ['dashboard','customers','leads','lead-followup','chat','media','products',\n" + indent + "'calc','quotes','orders','order-stats','lead-analytics','ar-dashboard',\n" + indent + "'commission','production','inventory','partners','purchase-orders',\n" + indent + "'catalog','email','ai','prompts','knowledge','scripts','countries',\n" + indent + "'reports','activity-logs',\n" + indent + "'v5-regions','v5-agents','v5-factories','v5-pricing','v5-leads','v5-dashboard','v6-pl','v6-invoices','v6-expenses','v6-budgets','v6-cashflow','v6-exec',\n" + indent + "'pub-dashboard','pub-accounts','pub-schedule','pub-content','pub-analytics','pub-comments','pub-reports'"

if sales_old in content:
    content = content.replace(sales_old, sales_new)
    print("Sales pages updated")
else:
    print("Sales pages NOT FOUND")

with open('templates/index.html', 'w', encoding='utf-8') as f:
    f.write(content)
print("Done")
