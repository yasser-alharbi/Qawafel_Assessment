"""Run with: python -m streamlit run app.py"""
import json
from pathlib import Path
import streamlit as st
import qawafel_store as store
import bank_review

ROOT=Path(__file__).resolve().parent
st.set_page_config(page_title='Qawafel | Financing Review',page_icon='📄',layout='wide')
st.title('Qawafel · Financing application')
st.caption('Applicant + Bank Review · بيانات وهمية للتجربة فقط')
db=store.connect()
def rerun():
    db.close()
    st.rerun()
if 'new_app_id' in st.session_state:
    st.session_state.chosen_app=st.session_state.pop('new_app_id')

with st.sidebar:
    st.header('Your requests')
    apps=store.rows(db,'SELECT * FROM application ORDER BY id DESC')
    choice=st.selectbox('Open a request',[None]+[a['id'] for a in apps],
                        format_func=lambda v:'Create a new request' if v is None else next(f"#{a['id']} — {a['business_name']} ({a['status']})" for a in apps if a['id']==v),key='chosen_app')
    st.info('Local demo: requests are saved on this computer. No bank connection or login is included.')

if choice is None:
    st.subheader('Create your application')
    st.write('حدد المنشأة والسنة والحسابات المطلوبة، ثم أنشئ الطلب.')
    with st.form('create'):
        name=st.text_input('Business name',value='Demo Noor Wholesale',help='Use the account holder printed on your statements. For the supplied PDFs, enter Demo Noor Wholesale.')
        year=st.number_input('Reporting year (January–December)',min_value=2000,max_value=2100,value=2025)
        accounts=st.text_area('Required account references — one per line',value='DEMO-ACCOUNT-001')
        if st.form_submit_button('Create request',type='primary'):
            try:
                new_id=store.create_application(db,name,int(year),accounts.splitlines())
                st.session_state.new_app_id=new_id
                rerun()
            except ValueError as exc: st.error(str(exc))
    db.close()
    st.stop()

app=store.application(db,choice)
locked=app['status']!='draft'
if not locked:
    with st.sidebar.expander('Manage draft'):
        confirm = st.checkbox(f"Permanently delete draft #{choice} — {app['business_name']} and its saved uploads", key=f'confirm_delete_{choice}')
        if st.button('Delete draft', disabled=not confirm, key=f'delete_draft_{choice}'):
            try:
                store.delete_draft(db, choice)
                st.session_state.new_app_id = None
                rerun()
            except ValueError as exc:
                st.error(str(exc))
with db:
    coverage=store.validate(db,choice)
current=store.issues(db,choice)
docs=store.documents(db,choice)
blocking=sum(i['severity']=='blocking' for i in current)
unexplained=sum(i['severity']=='warning' and not i['applicant_explanation'].strip() for i in current)

tab,bank_tab=st.tabs(['Applicant','Bank Review'])
with tab:
    st.subheader(f"{app['business_name']} · Request #{choice}")
    st.write(f"**Reporting period:** {app['period_start']} to {app['period_end']} · **Status:** {app['status']}")
    c1,c2,c3=st.columns(3)
    c1.metric('Included files',len(docs)); c2.metric('Blocking issues',blocking); c3.metric('Warnings needing explanation',unexplained)
    if locked:
        st.success('Submitted locally. This request is now read-only; it has not been sent to a bank.')
    if 'upload_results' in st.session_state:
        for message in st.session_state.pop('upload_results'): st.info(message)

    with st.expander('How to read the sample data / كيف تقرأ البيانات؟'):
        st.markdown('''**Excel:** each row is one invoice. `invoice_number` identifies it; `invoice_date` is its date; `total_amount` is the invoiced amount. The due date does not prove payment.

**PDF:** `Incoming` is money received, `Outgoing` is money paid out, and `Balance` is the balance after that transaction. A payment reference may contain an invoice number.

كل صف في إكسل يمثل فاتورة. في كشف الحساب، المبلغ الوارد ليس بالضرورة مبيعات؛ قد يكون قرضًا أو تحويلًا داخليًا.''')

    if not locked:
        st.subheader('1. Upload your documents')
        st.caption('XLSX/CSV: supplied invoice columns. PDF: supplied one-page Demo Bank format. Maximum 10 MB per file.')
        uploads=st.file_uploader('Invoice spreadsheets and bank statements',type=['xlsx','csv','pdf'],accept_multiple_files=True,key=f'uploads_{choice}')
        if st.button('Process uploaded files',disabled=not uploads):
            messages=[]
            with st.spinner('Reading files and checking coverage…'):
                for upload in uploads:
                    try:
                        did=store.upload(db,choice,upload.name,upload.getvalue())
                        d=db.execute('SELECT * FROM document WHERE id=?',(did,)).fetchone()
                        messages.append(f"{upload.name}: {d['processing_status']}." + (' See issues below.' if d['error'] else ''))
                    except ValueError as exc: messages.append(str(exc))
            st.session_state.upload_results=messages
            rerun()
        with st.expander('Try the supplied sample files'):
            sample_mode=st.radio('Sample selection',['All 12 months','Leave April out'],horizontal=True)
            if st.button('Load sample files'):
                files=[ROOT/'data/invoices/sample_invoices_2025.xlsx']+sorted((ROOT/'data/bank_statements').glob('*.pdf'))
                messages=[]
                with st.spinner('Reading the actual Excel and PDF files…'):
                    for path in files:
                        if sample_mode=='Leave April out' and path.name=='statement_2025-04.pdf': continue
                        try: store.upload(db,choice,path.name,path.read_bytes())
                        except ValueError as exc: messages.append(str(exc))
                st.session_state.upload_results=messages or ['Sample files processed.']
                rerun()

    st.subheader('2. Check coverage and issues')
    st.dataframe(coverage,hide_index=True,width='stretch')
    if not current: st.success('All checks passed.' if locked else 'All checks passed. The request is ready to submit.')
    for issue in current:
        with st.expander(f"{issue['severity'].upper()} · {issue['message']}"):
            st.write(issue['next_action'])
            text=st.text_area('Your explanation',value=issue['applicant_explanation'],key=f"explain_{choice}_{issue['id']}",disabled=locked)
            if st.button('Save explanation',key=f"save_{issue['id']}",disabled=locked):
                store.save_explanation(db,choice,issue['id'],text)
                rerun()
            if issue['severity']=='blocking': st.caption('An explanation is retained, but does not remove this blocker.')

    st.subheader('3. Review or replace files')
    if docs:
        st.dataframe([{'ID':d['id'],'File':d['file_name'],'Type':d['type'],'Result':d['processing_status']} for d in docs],hide_index=True,width='stretch')
        selected=st.selectbox('Choose a file',[d['id'] for d in docs],format_func=lambda v:next(d['file_name'] for d in docs if d['id']==v))
        d=next(d for d in docs if d['id']==selected)
        st.download_button('Download original',data=d['content'],file_name=d['file_name'])
        if not locked:
            replacement=st.file_uploader('Replacement file (same type)',type=['xlsx','csv','pdf'],key=f'replace_{choice}_{selected}')
            if st.button('Replace and recheck',disabled=replacement is None):
                try:
                    store.upload(db,choice,replacement.name,replacement.getvalue(),replaces=selected)
                    rerun()
                except ValueError as exc: st.error(str(exc))
            if st.button('Exclude selected file from this request'):
                store.exclude(db,choice,selected)
                rerun()
            st.caption('Original files and explanations remain in history. Excluded files can be uploaded again.')
    with st.expander('Extracted data and history'):
        st.dataframe(store.records(db,choice),hide_index=True,width='stretch')
        history=[{'ID':d['id'],'File':d['file_name'],'Included':bool(d['active']),'Replaces':d['replaces_document_id']} for d in store.documents(db,choice,active=False)]
        st.dataframe(history,hide_index=True,width='stretch')
        st.dataframe(store.issues(db,choice,history=True),hide_index=True,width='stretch')

    st.subheader('4. Submit')
    st.caption('Submission saves the request and unlocks Bank Review. No real bank delivery is performed.')
    if st.button('Submit application',type='primary',disabled=locked or blocking>0 or unexplained>0):
        try:
            store.submit(db,choice)
            rerun()
        except ValueError as exc: st.error(str(exc))
    st.download_button('Download request summary (JSON)',data=json.dumps(store.summary(db,choice),indent=2,ensure_ascii=False),file_name=f'application_{choice}.json',mime='application/json')
with bank_tab:
    bank_review.render(db,choice)
db.close()
