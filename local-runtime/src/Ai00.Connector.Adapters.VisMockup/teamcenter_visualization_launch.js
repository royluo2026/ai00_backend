var BufferedReader=Java.type('java.io.BufferedReader'),InputStreamReader=Java.type('java.io.InputStreamReader');
var Connection=Java.type('com.teamcenter.soa.client.Connection'),CredentialManager=Java.type('com.teamcenter.soa.client.CredentialManager'),SoaConstants=Java.type('com.teamcenter.soa.SoaConstants');
var SessionService=Java.type('com.teamcenter.services.strong.core.SessionService'),CoreDM=Java.type('com.teamcenter.services.strong.core.DataManagementService');
var VisDM=Java.type('com.teamcenter.services.rac.visualization._2013_05.DataManagement');
var ServerInfo=Java.type('com.teamcenter.services.rac.visualization._2011_02.DataManagement$ServerInfo'),UserAgent=Java.type('com.teamcenter.services.rac.visualization._2011_02.DataManagement$UserAgentDataInfo');
var Files=Java.type('java.nio.file.Files'),Paths=Java.type('java.nio.file.Paths'),StandardCharsets=Java.type('java.nio.charset.StandardCharsets'),UUID=Java.type('java.util.UUID');
var System=Java.type('java.lang.System');
function timed(phase,action){
  var start=System.nanoTime();
  try{return action();}
  finally{System.err.println('AI00_TC_TIMING_V1:'+JSON.stringify({phase:phase,elapsed_ms:Number(System.nanoTime()-start)/1000000}));}
}
function fail(code){throw new Error('AI00_CODE:'+code);}
function hex(bytes){var out='';Java.from(bytes).forEach(function(b){var n=Number(b)&255;out+=(n<16?'0':'')+n.toString(16);});return out.toUpperCase();}
function resolveDirectModelFile(dm,datasetUid){
  var loaded=dm.loadObjects(Java.to([datasetUid],'java.lang.String[]'));
  if(loaded.sizeOfPartialErrors()>0||loaded.sizeOfPlainObjects()!==1)fail('teamcenter_direct_model_dataset_unavailable');
  var dataset=loaded.getPlainObject(0);
  if(String(dataset.getUid())!==datasetUid)fail('teamcenter_direct_model_dataset_uid_mismatch');
  if(String(dataset.getTypeObject().getName())!=='DirectModel'&&!dataset.getTypeObject().isInstanceOf('DirectModel'))fail('teamcenter_direct_model_dataset_type_invalid');
  if(dm.getProperties(Java.to([dataset],'com.teamcenter.soa.client.model.ModelObject[]'),Java.to(['ref_list'],'java.lang.String[]')).sizeOfPartialErrors()>0)fail('teamcenter_direct_model_properties_failed');
  var files=Java.from(dataset.getPropertyObject('ref_list').getModelObjectArrayValue());
  if(files.length===0||files.length>128)fail('teamcenter_direct_model_file_ambiguous');
  if(dm.getProperties(Java.to(files,'com.teamcenter.soa.client.model.ModelObject[]'),Java.to(['original_file_name'],'java.lang.String[]')).sizeOfPartialErrors()>0)fail('teamcenter_direct_model_properties_failed');
  var candidates=[];
  files.forEach(function(file){var name=String(file.getPropertyObject('original_file_name').getDisplayableValue());if(/\.jt$/i.test(name))candidates.push({dataset_uid:datasetUid,file_uid:String(file.getUid()),file_name:name});});
  if(candidates.length!==1||!candidates[0].file_uid||candidates[0].file_name.length>512||/[\\/\x00-\x1f]/.test(candidates[0].file_name))fail('teamcenter_direct_model_file_ambiguous');
  return candidates[0];
}
function downloadDirectModelFile(dm,fms,source){
  var loaded=timed('file_load',function(){return dm.loadObjects(Java.to([source.file_uid],'java.lang.String[]'));});
  if(loaded.sizeOfPartialErrors()>0||loaded.sizeOfPlainObjects()!==1)fail('teamcenter_direct_model_file_unavailable');
  var file=loaded.getPlainObject(0);
  if(String(file.getUid())!==source.file_uid||!file.getTypeObject().isInstanceOf('ImanFile'))fail('teamcenter_direct_model_file_unavailable');
  var downloaded=timed('fms_get_files',function(){return fms.getFiles(Java.to([file],'com.teamcenter.soa.client.model.ModelObject[]'));});
  if(downloaded.sizeOfPartialErrors()>0||downloaded.sizeOfFiles()!==1)fail('teamcenter_direct_model_download_failed');
  return downloaded.getFile(0);
}
function closedKeys(value,keys){return value&&typeof value==='object'&&!Array.isArray(value)&&Object.keys(value).sort().join(',')===keys.slice().sort().join(',');}
function parseFrameLine(line){
  var prefix='AI00_TC_VIS_V2:';
  if(line.length>65536||line.indexOf(prefix)!==0)fail('teamcenter_worker_response_invalid');
  var text=line.substring(prefix.length),value=JSON.parse(text);
  // JSON.parse checks syntax; this second pass rejects duplicate keys lost by JSON.parse.
  var tokens=text.match(/"(?:\\.|[^"\\])*"|[{}\[\]:,]/g)||[],stack=[];
  for(var i=0;i<tokens.length;i++){
    var token=tokens[i];
    if(token==='{'||token==='['){stack.push(Object.create(null));if(stack.length>32)fail('teamcenter_worker_response_invalid');}
    else if(token==='}'||token===']')stack.pop();
    else if(token.charAt(0)==='"'&&tokens[i+1]===':'){
      var key=JSON.parse(token),keys=stack[stack.length-1];
      if(Object.prototype.hasOwnProperty.call(keys,key))fail('teamcenter_worker_response_invalid');keys[key]=true;
    }
  }
  return validateFrame(value);
}
function validateFrame(frame){
  if(!closedKeys(frame,['type','generation','request_id','payload'])||typeof frame.type!=='string'||typeof frame.generation!=='string'||!/^\d{1,19}$/.test(frame.generation)||typeof frame.request_id!=='string'||! /^[a-f0-9]{32}$/.test(frame.request_id)||!frame.payload||typeof frame.payload!=='object'||Array.isArray(frame.payload))fail('teamcenter_worker_response_invalid');
  return frame;
}
function errorCode(error){
  var match=/AI00_CODE:(teamcenter_[a-z_]+)/.exec(String(error&&error.message||''));
  var code=match?match[1]:'';
  var allowed=['teamcenter_authentication_failed','teamcenter_session_expired','teamcenter_object_not_found','teamcenter_source_selector_invalid','teamcenter_visualization_operation_invalid','teamcenter_visualization_launch_info_failed','teamcenter_visualization_launch_info_invalid','teamcenter_direct_model_dataset_unavailable','teamcenter_direct_model_dataset_uid_mismatch','teamcenter_direct_model_dataset_type_invalid','teamcenter_direct_model_properties_failed','teamcenter_direct_model_file_ambiguous','teamcenter_direct_model_file_unavailable','teamcenter_direct_model_download_failed','teamcenter_visualization_consumer_failed','teamcenter_worker_response_invalid'];
  return allowed.indexOf(code)>=0?code:'teamcenter_visualization_launch_failed';
}
function runSession(io,sdk){
  var session=null,current=null,generation=null;
  function send(type,payload){io.write({type:type,generation:generation,request_id:current.request_id,payload:payload});}
  try{
    current=validateFrame(io.read());generation=current.generation;
    if(current.type!=='login'||!closedKeys(current.payload,['endpoint_id','username','password'])||current.payload.endpoint_id!=='tc-production')fail('teamcenter_worker_response_invalid');
    session=sdk.login(current.payload);current.payload={};send('ready',{});
    while(true){
      var next=io.read();if(next===null)break;
      current=validateFrame(next);
      if(current.generation!==generation)fail('teamcenter_worker_response_invalid');
      if(current.type==='logout'){
        if(!closedKeys(current.payload,[]))fail('teamcenter_worker_response_invalid');
        session.logout();session=null;send('closed',{});break;
      }
      if(current.type!=='consume')fail('teamcenter_worker_response_invalid');
      var material;
      try{
        material=session.prepare(current.payload);send('material_ready',material);
        var ack=validateFrame(io.read());
        if(ack.generation!==generation||ack.request_id!==current.request_id||!closedKeys(ack.payload,[])||(ack.type!=='material_consumed'&&ack.type!=='material_failed'))fail('teamcenter_worker_response_invalid');
        if(ack.type==='material_failed')fail('teamcenter_visualization_consumer_failed');
      }finally{session.cleanup();}
      send('result',{ok:true,result:{launch_id:sdk.launchId(),runner_started:true,expected_visdoc_uid:material.expected_visdoc_uid,source_identity_hash:material.source_identity_hash}});
    }
  }catch(error){if(current&&generation)send('result',{ok:false,code:errorCode(error)});}
  finally{if(session){try{session.logout();}catch(ignore){}}}
}
function loginSdk(payload){
  var state={user:String(payload.username||''),password:String(payload.password||''),group:'',role:'',authenticating:true};
  if(!state.user||state.user.length>256||!state.password||state.password.length>4096)fail('teamcenter_authentication_failed');
  var CredentialImpl=Java.extend(CredentialManager,{getCredentialType:function(){return CredentialManager.CLIENT_CREDENTIAL_TYPE_STD;},getCredentials:function(){if(!state.authenticating)fail('teamcenter_session_expired');return Java.to([state.user,state.password,state.group,state.role],'java.lang.String[]');},setUserPassword:function(){},setGroupRole:function(g,r){state.group=String(g||'');state.role=String(r||'');}});
  var connection=new Connection('http://192.168.44.150:7001/tc',new CredentialImpl(),SoaConstants.REST,SoaConstants.HTTP);
  connection.setApplicationName('AI00 Read-only VisMockup Launch');
  var session=SessionService.getService(connection),fms=null,vviFile=null,jtFile=null;
  try{var login=timed('login',function(){return session.login(state.user,state.password,'','','zh_CN','AI00ReadOnlyVisualization');});if(!login||!login.user)fail('teamcenter_authentication_failed');}
  catch(error){connection.release();throw error;}
  finally{state.authenticating=false;state.user='';state.password='';payload.username='';payload.password='';}
  function prepare(payload){
  var selector=payload.source_selector||{};
  if(!closedKeys(payload,['source_selector','expected_visdoc_uid','source_identity_hash','material_root','visualization_operation'])||selector.endpoint_id!=='tc-production'||!selector.object_uid||!payload.material_root)fail('teamcenter_source_selector_invalid');
  var visualizationOperation=String(payload.visualization_operation||'');if(visualizationOperation!=='Open'&&visualizationOperation!=='Insert')fail('teamcenter_visualization_operation_invalid');
  var loaded=timed('source_load',function(){return CoreDM.getService(connection).loadObjects(Java.to([String(selector.object_uid)],'java.lang.String[]'));});var target=loaded.sizeOfPlainObjects()>0?loaded.getPlainObject(0):loaded.sizeOfUpdatedObjects()>0?loaded.getUpdatedObject(0):null;if(!target||loaded.sizeOfPartialErrors()>0)fail('teamcenter_object_not_found');
  var id=new VisDM.IdInfo2();id.object=target;id.operation=visualizationOperation;id.structureMode='None';id.clientId='AI00';
  var server=new ServerInfo();server.protocol='http';server.hostpath='http://192.168.44.150:7001/tc';server.servermode=0;
  var agent=new UserAgent();agent.userApplication='RAC';agent.userAppVersion='14.2.0.2(20230301.00)';
  var sessionInfo=new VisDM.SessionInfo2();sessionInfo.sessionDescriminator='226TCSession';sessionInfo.hasTransientVolume=false;
  var ids=Java.to([id],'com.teamcenter.services.rac.visualization._2013_05.DataManagement$IdInfo2[]');
  var response=timed('launch_info',function(){return connection.getSender().invoke3('Visualization-2013-05-DataManagement','createLaunchInfo',Java.to([ids,server,agent,sessionInfo],'java.lang.Object[]'),VisDM.class);});
  if(!response||response.serviceData.sizeOfPartialErrors()>0||!response.vviStrBuffersOutputMap||response.vviStrBuffersOutputMap.isEmpty())fail('teamcenter_visualization_launch_info_failed');
  var vvi=String(response.vviStrBuffersOutputMap.values().iterator().next());
  if(!/^Operation=[^\r\n]*$/m.test(vvi)||!/^OperationStructure=[^\r\n]*$/m.test(vvi))fail('teamcenter_visualization_launch_info_invalid');
  vvi=vvi.replace(/^Operation=[^\r\n]*$/m,'Operation='+visualizationOperation).replace(/^OperationStructure=[^\r\n]*$/m,'OperationStructure=None');
  if(!new RegExp('^Operation='+visualizationOperation+'$','m').test(vvi)||!/^OperationStructure=None$/m.test(vvi))fail('teamcenter_visualization_launch_info_invalid');
  var sourceEvidence=null;
  if(/^VisDoc_Type=DirectModel\r?$/m.test(vvi)){
    var datasetMatch=/^VisDoc_UID=([^\r\n]+)\r?$/m.exec(vvi);
    if(!datasetMatch)fail('teamcenter_direct_model_dataset_unavailable');
    sourceEvidence=timed('dataset_resolve',function(){return resolveDirectModelFile(CoreDM.getService(connection),decodeURIComponent(datasetMatch[1]));});
  }
  var materialRoot=Paths.get(String(payload.material_root));Files.createDirectories(materialRoot);
  if(sourceEvidence){
    var FileManagementUtility=Java.type('com.teamcenter.soa.client.FileManagementUtility');
    if(!fms)fms=timed('fms_init',function(){return new FileManagementUtility(connection);});
    var localFile=downloadDirectModelFile(CoreDM.getService(connection),fms,sourceEvidence);
    jtFile=Files.createTempFile(materialRoot,'ai00-tc-model-','.jt');
    Files.copy(localFile.toPath(),jtFile,Java.type('java.nio.file.StandardCopyOption').REPLACE_EXISTING);
  }else{
    vviFile=Files.createTempFile(materialRoot,'ai00-tc-vis-','.vvi');Files.write(vviFile,new java.lang.String(vvi).getBytes(StandardCharsets.UTF_8));
  }
  vvi='';
  return {type:'material_ready',material_path:String((jtFile||vviFile).toAbsolutePath()),expected_visdoc_uid:String(payload.expected_visdoc_uid||''),source_identity_hash:String(payload.source_identity_hash||'')};
  }
  return {prepare:prepare,cleanup:function(){
    try{if(jtFile)Files.deleteIfExists(jtFile);}catch(ignore){}finally{jtFile=null;}
    try{if(vviFile)Files.deleteIfExists(vviFile);}catch(ignore){}finally{vviFile=null;}
  },logout:function(){try{timed('logout',function(){session.logout();});}finally{connection.release();}}};
}
var input=new BufferedReader(new InputStreamReader(System['in'],'UTF-8'));
runSession({read:function(){
  var line='',ch;
  while((ch=input.read())!==-1&&ch!==10){if(line.length>=65536)fail('teamcenter_worker_response_invalid');line+=String.fromCharCode(ch);}
  if(ch===-1&&line.length===0)return null;
  if(line.indexOf('AI00_TC_VIS_V2:')!==0||new java.lang.String(line).getBytes(StandardCharsets.UTF_8).length>65536)fail('teamcenter_worker_response_invalid');
  return parseFrameLine(line);
},write:function(frame){print('AI00_TC_VIS_V2:'+JSON.stringify(frame));System.out.flush();}},
{login:loginSdk,launchId:function(){return 'tclaunch:'+String(UUID.randomUUID()).replace(/-/g,'')+String(UUID.randomUUID()).replace(/-/g,'');}});
