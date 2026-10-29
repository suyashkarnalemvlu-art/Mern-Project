function filterTable(inputId, tableId){
 const q=document.getElementById(inputId).value.toLowerCase();
 document.querySelectorAll("#"+tableId+" tr").forEach((row,i)=>{
   if(i===0)return;
   row.style.display=row.innerText.toLowerCase().includes(q)?"":"none";
 });
}
function drawBars(id,labels,values){
 const c=document.getElementById(id); if(!c)return;
 const ctx=c.getContext("2d"), w=c.width=c.clientWidth*2, h=c.height=c.clientHeight*2;
 ctx.scale(2,2); const W=c.clientWidth,H=c.clientHeight;
 ctx.clearRect(0,0,W,H);
 const max=Math.max(...values,1), bw=Math.max(18,(W-50)/Math.max(values.length,1)-12);
 labels.forEach((label,i)=>{
   const x=35+i*(bw+12), bh=(values[i]/max)*(H-45);
   ctx.fillStyle="#1769aa";ctx.fillRect(x,H-25-bh,bw,bh);
   ctx.fillStyle="#5d6878";ctx.font="11px Arial";ctx.fillText(label.substring(0,12),x,H-8);
 });
}