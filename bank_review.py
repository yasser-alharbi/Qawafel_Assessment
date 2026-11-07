"""Conservative, deterministic payment suggestions; never confirms settlement."""
from collections import defaultdict
from decimal import Decimal
import re
import qawafel_store as store


def suggest(records):
    invoices=[r for r in records if r['type']=='invoice']
    payments=[r for r in records if r['type']=='bank_transaction' and r['direction']=='incoming']
    links=[]
    excluded=[]
    for payment in payments:
        description=(payment['description']+' '+payment['reference']).lower()
        if any(term in description for term in ('internal transfer','own-transfer','loan')):
            excluded.append(payment)
            continue
        eligible=[i for i in invoices if i['currency']==payment['currency'] and i['record_date']<=payment['record_date']]
        explicit=[i for i in eligible if re.search(r'(?<![\w-])'+re.escape(i['reference'])+r'(?![\w-])',payment['reference'],re.I)]
        if explicit:
            combined=len(explicit)>1
            exact=Decimal(payment['amount'])==sum((Decimal(i['amount']) for i in explicit),Decimal(0))
            for invoice in explicit:
                amount=invoice['amount'] if combined and exact else payment['amount'] if not combined else None
                links.append({'invoice_record_id':invoice['id'],'payment_record_id':payment['id'],
                              'suggested_amount':amount,'kind':'Combined reference' if combined and exact else 'Reference' if not combined else 'Review amount mismatch'})
        elif not payment['reference'].strip():
            for invoice in eligible:
                if (Decimal(invoice['amount'])==Decimal(payment['amount']) and
                    invoice['counterparty'].strip().casefold()==payment['description'].strip().casefold()):
                    links.append({'invoice_record_id':invoice['id'],'payment_record_id':payment['id'],
                                  'suggested_amount':None,'kind':'Uncertain: same customer and amount'})
    # If multiple references over-allocate any invoice, keep the evidence but remove
    # allocations for the affected payments, including their combined-payment links.
    totals=defaultdict(lambda:Decimal(0))
    for link in links:
        if link['suggested_amount'] is not None:
            totals[link['invoice_record_id']]+=Decimal(link['suggested_amount'])
    excess={i['id'] for i in invoices if totals[i['id']]>Decimal(i['amount'])}
    disputed={l['payment_record_id'] for l in links if l['invoice_record_id'] in excess}
    for link in links:
        if link['payment_record_id'] in disputed:
            link.update(suggested_amount=None,kind='Review amount mismatch')
    return links,excluded


def review(db,app_id):
    if store.application(db,app_id)['status']=='draft':
        raise ValueError('Submit the application before opening bank review.')
    records=store.records(db,app_id)
    links,excluded=suggest(records)
    with db:
        db.execute('''DELETE FROM payment_suggestion WHERE invoice_record_id IN
                      (SELECT r.id FROM financial_record r JOIN document d ON d.id=r.document_id WHERE d.application_id=?)''',(app_id,))
        for l in links:
            db.execute('INSERT INTO payment_suggestion (invoice_record_id,payment_record_id,suggested_amount) VALUES (?,?,?)',
                       (l['invoice_record_id'],l['payment_record_id'],l['suggested_amount']))
    overview=[]
    for invoice in [r for r in records if r['type']=='invoice']:
        related=[l for l in links if l['invoice_record_id']==invoice['id']]
        allocated=sum((Decimal(l['suggested_amount']) for l in related if l['suggested_amount'] is not None),Decimal(0))
        if not related: status='No matching payment identified'
        elif any(l['suggested_amount'] is None for l in related): status='Needs review: uncertain match'
        elif allocated<Decimal(invoice['amount']): status='Partial amount suggested'
        else: status='Full amount suggested'
        overview.append({'id':invoice['id'],'Invoice':invoice['reference'],'Date':invoice['record_date'],
                         'Customer':invoice['counterparty'],'Invoice amount (SAR)':invoice['amount'],
                         'Suggested allocation (SAR)':str(allocated) if allocated else None,'Review status':status})
    return records,links,excluded,overview


def render(db,app_id):
    import streamlit as st
    import json
    import io
    import zipfile
    st.subheader('Bank Review')
    st.caption('اقتراحات للمراجعة، وليست تأكيدًا للسداد أو قرارًا بالتمويل.')
    if store.application(db,app_id)['status']=='draft':
        st.info('Submit the request in Applicant first. Then review its invoices and evidence here.')
        return
    records,links,excluded,overview=review(db,app_id)
    index={r['id']:r for r in records}
    docs={d['id']:d for d in store.documents(db,app_id,active=False)}
    cols=st.columns(3)
    cols[0].metric('Invoices',len(overview))
    cols[1].metric('Partial / uncertain',sum(o['Review status'] in ('Partial amount suggested','Needs review: uncertain match') for o in overview))
    cols[2].metric('No payment identified',sum(o['Review status']=='No matching payment identified' for o in overview))
    st.dataframe([{k:v for k,v in o.items() if k!='id'} for o in overview],hide_index=True,width='stretch')
    invoice_id=st.selectbox('Inspect an invoice',[o['id'] for o in overview],format_func=lambda n:index[n]['reference'],key=f'bank_invoice_{app_id}')
    invoice=index[invoice_id]
    st.write(f"**{invoice['reference']}** · {invoice['amount']} {invoice['currency']} · {invoice['counterparty']}")
    source=docs[invoice['document_id']]
    st.caption(f"Invoice source: {source['file_name']} — {invoice['source_location']}")
    st.download_button('Download invoice source',source['content'],file_name=source['file_name'],key=f'bank_invoice_source_{app_id}')
    related=[l for l in links if l['invoice_record_id']==invoice_id]
    if not related: st.info('No matching payment identified. This does not establish that the invoice is unpaid.')
    for link in related:
        payment=index[link['payment_record_id']]
        source=docs[payment['document_id']]
        with st.container(border=True):
            st.write(f"**{payment['record_date']} · Receipt: {payment['amount']} SAR**")
            st.write(f"{link['kind']} · Proposed allocation: {link['suggested_amount'] or 'Not allocated'}")
            st.write(f"Reference: {payment['reference'] or 'No invoice reference'}")
            st.caption(f"{source['file_name']} — {payment['source_location']}")
            st.download_button('Download statement source',source['content'],file_name=source['file_name'],key=f"statement_{app_id}_{invoice_id}_{payment['id']}")
    st.subheader('Applicant warnings and explanations')
    all_issues=store.issues(db,app_id,history=True)
    notable=[i for i in all_issues if i['status']=='open' or i['applicant_explanation']]
    if notable:
        st.dataframe([{'Status':i['status'],'Severity':i['severity'],'Issue':i['message'],
                       'Explanation':i['applicant_explanation'] or 'Not provided'} for i in notable],hide_index=True,width='stretch')
    else: st.write('No outstanding warnings or applicant explanations.')
    with st.expander('Excluded inflows and matching rules'):
        st.write('Outgoing transactions are not payment candidates. Known loan and own-account transfer descriptions are excluded. Reference matches take priority. Amount/customer-only candidates remain unallocated. Payments dated before an invoice are not matched.')
        st.dataframe([{'Date':r['record_date'],'Amount':r['amount'],'Description':r['description'],'Source':r['source_location']} for r in excluded],hide_index=True,width='stretch')
        st.caption('This is a small rule-based prototype, not a bank credit policy. Unrecognised descriptions can still require human review.')
    package=store.summary(db,app_id)
    package.update(payment_suggestions=links,invoice_review=overview,excluded_inflows=excluded)
    buffer=io.BytesIO()
    with zipfile.ZipFile(buffer,'w',zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('review.json',json.dumps(package,indent=2,ensure_ascii=False))
        for doc in docs.values():
            archive.writestr(f"sources/{doc['id']}_{doc['file_name']}",doc['content'])
    st.download_button('Download review package (ZIP)',buffer.getvalue(),file_name=f'review_{app_id}.zip',mime='application/zip')
    st.caption('The package contains the review summary and source documents, including retained history. Nothing is sent to a real bank.')
