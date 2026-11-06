import fs from 'node:fs/promises';
import { existsSync } from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath,pathToFileURL } from 'node:url';
import { createRequire } from 'node:module';
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';

const here=path.dirname(fileURLToPath(import.meta.url));
const args=process.argv.slice(2), options={};
for(let i=0;i<args.length;i+=2){if(!['--job','--output'].includes(args[i])||!args[i+1])throw new Error('Usage: fill_forms.mjs --job <job.json> --output <new-output-directory>');options[args[i].slice(2)]=args[i+1];}
if(!options.job||!options.output)throw new Error('Both --job and --output are required.');
const jobPath=path.resolve(options.job),out=path.resolve(options.output);
const master=path.join(here,'reimbursement-forms.xlsx');
if(out===here)throw new Error('Use a new claim-output directory; do not overwrite the master.');
const job=JSON.parse((await fs.readFile(jobPath,'utf8')).replace(/^\uFEFF/,''));
const type=job.claim_type, warnings=[];
if(job.schema_version!==1||!['travel','reception','expense'].includes(type))throw new Error('Expected schema_version1 and travel/reception/expense claim_type.');
if(!Array.isArray(job.expenses)||!Array.isArray(job.evidence))throw new Error('expenses and evidence must be arrays.');
if(job.claim?.attachment_count!=null)throw new Error('Paper attachment count must remain blank/null.');
if(job.claim?.subject_name!==undefined&&(typeof job.claim.subject_name!=='string'||/[\r\n]/.test(job.claim.subject_name)))throw new Error('claim.subject_name must be a single-line name string; it is not the payer or recipient.');
if(job.claim?.single_traveler!==undefined&&typeof job.claim.single_traveler!=='boolean')throw new Error('claim.single_traveler must be boolean.');
if(job.claim?.single_traveler&&(type!=='travel'||!job.claim?.subject_name?.trim()))throw new Error('single_traveler requires a travel claim and explicit subject_name.');
const ids=new Set(),evidenceIds=new Set();
for(const e of job.evidence){if(!e.id||evidenceIds.has(e.id))throw new Error('Evidence IDs must be unique and nonempty.');evidenceIds.add(e.id);}
function money(v,label){if(v==null||v==='')throw new Error(`${label}: amount missing; draft cannot silently print an incomplete total.`);const text=String(v);if(!/^\d+(\.\d{1,2})?$/.test(text))throw new Error(`${label}: expected nonnegative RMB amount with at most two decimal places.`);const n=Number(text);if(!Number.isFinite(n)||n>=100000000)throw new Error(`${label}: amount exceeds template range.`);return Math.round(n*100)/100;}
for(const e of job.expenses){if(!e.id||ids.has(e.id))throw new Error('Expense IDs must be unique and nonempty.');ids.add(e.id);if(!Array.isArray(e.evidence_ids)||e.evidence_ids.some(id=>!evidenceIds.has(id)))throw new Error(`Expense ${e.id}: unknown/missing evidence_ids.`);}
const ancillaryAmounts=new Map(), ancillaryEvidence=new Map();
for(const e of job.expenses){
 if(job.claim?.single_traveler&&e.category==='flight'&&e.ticket_count!==1)throw new Error(`Expense ${e.id}: individual flight leg requires ticket_count 1.`);
 if(e.other_amount==null)continue;
 if(type!=='travel'||!['flight','rail'].includes(e.category))throw new Error(`Expense ${e.id}: other_amount is allowed only on a travel flight/rail leg.`);
 const extra=money(e.other_amount,`Expense ${e.id} other_amount`);ancillaryAmounts.set(e.id,extra);
 if(extra>0){
  const links=e.other_evidence_ids;
  if(!Array.isArray(links)||!links.length||new Set(links).size!==links.length||links.some(id=>!e.evidence_ids.includes(id)))throw new Error(`Expense ${e.id}: positive other_amount requires unique other_evidence_ids included in evidence_ids.`);
  for(const id of links){if(ancillaryEvidence.has(id))throw new Error(`Ancillary evidence ${id} is claimed on multiple legs.`);ancillaryEvidence.set(id,e.id);}
 }
}
for(const e of job.expenses){if(e.category!=='other')continue;for(const id of e.evidence_ids){if(ancillaryEvidence.has(id)&&ancillaryEvidence.get(id)!==e.id)throw new Error(`Expense ${e.id}: ancillary evidence ${id} is already claimed on its linked leg; remove the duplicate claim.`);}}
const maxRows=type==='travel'?6:9;
if(job.expenses.length>maxRows)throw new Error(`Template capacity ${maxRows} rows exceeded (${job.expenses.length}). Split into a continuation; no rows were truncated.`);
const profile={organization:'',department:'',handler:'',recipient:'',bank:'',account:'',...job.profile};
if(typeof profile.account!=='string')throw new Error('Bank account must be a string to preserve all digits.');
if(!profile.bank||!profile.account)warnings.push('Bank/account missing; printable bank fields remain blank.');
if(job.expenses.length===0)warnings.push('No expense lines supplied; this is an unfilled draft.');
const require=createRequire(import.meta.url);
const runtimeCandidates=[here,process.env.CODEX_BUNDLED_NODE_ROOT,path.resolve(path.dirname(process.execPath),'..'),path.join(os.homedir(),'.cache','codex-runtimes','codex-primary-runtime','dependencies','node')].filter(Boolean);
let modulePath;
for(const runtime of runtimeCandidates){try{modulePath=require.resolve('@oai/artifact-tool',{paths:[runtime]});break;}catch(err){if(err.code!=='MODULE_NOT_FOUND')throw err;}}
if(!modulePath)throw new Error('Codex @oai/artifact-tool is required. Discover workspace dependencies or set CODEX_BUNDLED_NODE_ROOT to its Node dependency root.');
const {SpreadsheetFile,FileBlob}=await import(pathToFileURL(modulePath).href);
const wb=await SpreadsheetFile.importXlsx(await FileBlob.load(master));
const expense=wb.worksheets.getItem('费用报销单'),travel=wb.worksheets.getItem('差旅费报销单'),application=wb.worksheets.getItem('业务招待申请单'),guide=wb.worksheets.getItem('填写说明');
function text(s,c,value){if(value==null||value==='')return;const v=String(value);s.getRange(c).values=[[v.startsWith('=')?"'"+v:v]];}
function number(s,c,value,label){if(value==null||value==='')return;s.getRange(c).values=[[money(value,label)]];}
function count(s,c,value,label){if(value==null)return;if(!Number.isInteger(value)||value<0)throw new Error(`${label} must be a known nonnegative integer.`);s.getRange(c).values=[[value]];s.getRange(c).setNumberFormat('0');}
function dateValue(value,label){if(value==null||value==='')return null;if(!/^\d{4}-\d{2}-\d{2}$/.test(value))throw new Error(`${label} must be ISO YYYY-MM-DD.`);const d=new Date(`${value}T12:00:00Z`);if(!Number.isFinite(d.valueOf())||d.toISOString().slice(0,10)!==value)throw new Error(`${label}: invalid date.`);return d;}
function dateCell(s,c,value,label){const d=dateValue(value,label);if(!d)return;s.getRange(c).values=[[d]];s.getRange(c).setNumberFormat('yyyy"年"m"月"d"日"');}
for(const [key,cell] of Object.entries({department:'B4',handler:'B5',recipient:'B6',bank:'B7',account:'B8'})){guide.getRange(cell).values=[[profile[key]||'']];}
if(profile.organization)text(guide,'B9',profile.organization);
guide.getRange('B8').setNumberFormat('@');
dateCell(expense,'T3',job.claim?.date,'Claim date');dateCell(travel,'M3',job.claim?.date,'Claim date');
if(job.claim?.subject_name!==undefined){const sheet=type==='travel'?travel:expense;sheet.getRange(type==='travel'?'K1':'T1').values=[['']];text(sheet,type==='travel'?'K1':'T1',job.claim.subject_name.trim());}
const labels={flight:'机票',rail:'火车票',taxi:'交通费',meal:'餐费',hotel:'住宿费',other:'其他费用',reception:'招待费用'};
let total=0;
if(type==='travel'){
 for(let i=0;i<job.expenses.length;i++){
  const e=job.expenses[i],r=7+i,amount=money(e.amount,`Expense ${e.id}`),d=dateValue(e.date,`Expense ${e.id} date`);
  if(!['flight','rail','taxi','meal','hotel','other'].includes(e.category))throw new Error(`Expense ${e.id}: category not supported on travel form.`);
  if(d){travel.getRange(`A${r}`).values=[[d.getUTCMonth()+1]];travel.getRange(`B${r}`).values=[[d.getUTCDate()]];}
  text(travel,`C${r}`,e.purpose);text(travel,`D${r}`,e.origin);text(travel,`E${r}`,e.destination);
  const c=({flight:'G',rail:'G',hotel:'I',taxi:'K',meal:'M',other:'N'})[e.category];travel.getRange(`${c}${r}`).values=[[amount]];
  const extra=ancillaryAmounts.get(e.id)||0;if(ancillaryAmounts.has(e.id))travel.getRange(`N${r}`).values=[[extra]];
  if(['flight','rail'].includes(e.category))count(travel,`F${r}`,e.ticket_count,'Ticket count');
  if(e.category==='hotel')count(travel,`H${r}`,e.ticket_count,'Hotel document count');
  if(e.category==='meal')count(travel,`L${r}`,e.meal_count,'Actual meal count');
  // Map supplied taxi/meal amounts directly; do not infer quantities or reimbursement rates.
  total+=amount+extra;
 }
}else{
 for(let i=0;i<job.expenses.length;i++){
  const e=job.expenses[i],r=7+i,amount=money(e.amount,`Expense ${e.id}`);
  if(!labels[e.category])throw new Error(`Expense ${e.id}: unsupported category.`);
  text(expense,`A${r}`,labels[e.category]);text(expense,`F${r}`,e.purpose);expense.getRange(`AA${r}`).values=[[amount]];total+=amount;
 }
 if(type==='reception'){
 const a=job.reception_application||{};
 dateCell(application,'I3',a.application_date,'Application date');
 text(application,'G4',a.guest);count(application,'L4',a.guest_count??a.headcount,'Guest count');
 const eventDate=a.date||a.reception_date;if(eventDate)dateValue(eventDate,'Reception date');
 text(application,'C5',[eventDate,a.time||a.reception_time].filter(Boolean).join(' '));text(application,'G5',a.location);
 number(application,'L5',a.estimated_amount??a.estimated_budget,'Estimated reception budget');
 text(application,'C6',Array.isArray(a.host_attendees)?a.host_attendees.join('、'):a.host_attendees);text(application,'C8',a.purpose);
 if(a.estimated_amount==null&&a.estimated_budget==null)warnings.push('Reception prior estimated budget missing; not replaced with actual receipts.');
 }
}
total=Math.round(total*100)/100;if(total>=100000000)throw new Error('Total exceeds template range.');
wb.recalculate();
const totalCell=type==='travel'?travel.getRange('O13'):expense.getRange('V16');
const actual=totalCell.values[0][0];
if(job.expenses.length){if(typeof actual!=='number'||Math.abs(actual-total)>0.001)throw new Error(`Recalculated total ${actual} does not reconcile to ${total}.`);}
const errors=await wb.inspect({kind:'match',searchTerm:'#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!|#SPILL!|#CALC!',options:{useRegex:true,maxResults:30},summary:'filled form formula errors'});
if(!errors.ndjson.includes('matched 0 entries'))throw new Error(`Formula error scan requires review: ${errors.ndjson}`);
await fs.mkdir(out,{recursive:true});
const target=path.join(out,`reimbursement-${type}-draft.xlsx`);
try{await fs.access(target);throw new Error(`Output exists; choose a new output directory: ${target}`);}catch(err){if(err.code!=='ENOENT')throw err;}
const xlsx=await SpreadsheetFile.exportXlsx(wb);await xlsx.save(target);
const python=process.env.CODEX_BUNDLED_PYTHON||[path.join(os.homedir(),'.cache','codex-runtimes','codex-primary-runtime','dependencies','python','python.exe'),path.resolve(path.dirname(process.execPath),'..','..','python','python.exe')].find(p=>existsSync(p))||(process.platform==='win32'?'python':'python3');
await promisify(execFile)(python,[path.join(here,'preserve_print_layout.py'),'--master',master,'--filled',target,'--active-sheet',type==='travel'?'1':'0']);
const printSheets=type==='travel'?['差旅费报销单']:type==='expense'?['费用报销单']:['费用报销单','业务招待申请单'];
const report={schema_version:1,status:'needs_review',claim_type:type,job_path:jobPath,output:target,print_sheets:printSheets,claimed_total_rmb:total,expense_rows_written:job.expenses.length,subject_name:job.claim?.subject_name??null,remarks_mode:job.claim?.subject_name!==undefined?'subject_name_only':'template_default',single_traveler:job.claim?.single_traveler??false,ancillary_amount_rmb:[...ancillaryAmounts.values()].reduce((a,b)=>Math.round((a+b)*100)/100,0),evidence_amounts_added_to_claim:false,traffic_quantity_field:'blank',attachment_count:'blank',signatures:'blank',warnings,formula_error_scan:errors.ndjson,print_size_mm:{cover:[220,136],application:[198.12,86.49]},print_scale_percent:{cover:100,application:90},worksheet_geometry_mm:{application:[220.133,96.097]},application_enclosing_print_box_mm:[199,87],physical_print_verified:false};
await fs.writeFile(path.join(out,'filled-form-report.json'),JSON.stringify(report,null,2));
console.log(JSON.stringify(report));
