var BufferedReader=Java.type('java.io.BufferedReader'),InputStreamReader=Java.type('java.io.InputStreamReader');
var Connection=Java.type('com.teamcenter.soa.client.Connection'),CredentialManager=Java.type('com.teamcenter.soa.client.CredentialManager'),SoaConstants=Java.type('com.teamcenter.soa.SoaConstants');
var SessionService=Java.type('com.teamcenter.services.strong.core.SessionService'),CoreDM=Java.type('com.teamcenter.services.strong.core.DataManagementService');
var VisDM=Java.type('com.teamcenter.services.rac.visualization._2013_05.DataManagement');
var ServerInfo=Java.type('com.teamcenter.services.rac.visualization._2011_02.DataManagement$ServerInfo'),UserAgent=Java.type('com.teamcenter.services.rac.visualization._2011_02.DataManagement$UserAgentDataInfo');
var Files=Java.type('java.nio.file.Files'),StandardCharsets=Java.type('java.nio.charset.StandardCharsets'),TimeUnit=Java.type('java.util.concurrent.TimeUnit'),UUID=Java.type('java.util.UUID');
function fail(code){throw new Error('AI00_CODE:'+code);}
function hex(bytes){var out='';Java.from(bytes).forEach(function(b){var n=Number(b)&255;out+=(n<16?'0':'')+n.toString(16);});return out.toUpperCase();}
var input=new BufferedReader(new InputStreamReader(java.lang.System['in'],'UTF-8'));
var state={user:String(input.readLine()||''),password:String(input.readLine()||''),group:'',role:''};
var request=JSON.parse(String(input.readLine()||'{}')),payload=request.payload||{},selector=payload.source_selector||{};
var CredentialImpl=Java.extend(CredentialManager,{getCredentialType:function(){return CredentialManager.CLIENT_CREDENTIAL_TYPE_STD;},getCredentials:function(){return Java.to([state.user,state.password,state.group,state.role],'java.lang.String[]');},setUserPassword:function(u,p){state.user=String(u||'');state.password=String(p||'');},setGroupRole:function(g,r){state.group=String(g||'');state.role=String(r||'');}});
var connection=null,session=null,vviFile=null,exitCode=1;
try{
  if(request.command!=='launch'||selector.endpoint_id!=='tc-production'||!selector.object_uid)fail('teamcenter_source_selector_invalid');
  connection=new Connection('http://192.168.44.150:7001/tc',new CredentialImpl(),SoaConstants.REST,SoaConstants.HTTP);connection.setApplicationName('AI00 Read-only VisMockup Launch');
  session=SessionService.getService(connection);var login=session.login(state.user,state.password,'','','zh_CN','AI00ReadOnlyVisualization');if(!login||!login.user)fail('teamcenter_authentication_failed');
  var loaded=CoreDM.getService(connection).loadObjects(Java.to([String(selector.object_uid)],'java.lang.String[]'));var target=loaded.sizeOfPlainObjects()>0?loaded.getPlainObject(0):loaded.sizeOfUpdatedObjects()>0?loaded.getUpdatedObject(0):null;if(!target||loaded.sizeOfPartialErrors()>0)fail('teamcenter_object_not_found');
  var id=new VisDM.IdInfo2();id.object=target;id.operation='Interop';id.structureMode='None';id.clientId='AI00';
  var server=new ServerInfo();server.protocol='http';server.hostpath='http://192.168.44.150:7001/tc';server.servermode=0;
  var agent=new UserAgent();agent.userApplication='RAC';agent.userAppVersion='14.2.0.2(20230301.00)';
  var sessionInfo=new VisDM.SessionInfo2();sessionInfo.sessionDescriminator='226TCSession';sessionInfo.hasTransientVolume=false;
  var response=connection.getSender().invoke3('Visualization-2013-05-DataManagement','createLaunchInfo',Java.to([[id],server,agent,sessionInfo],'java.lang.Object[]'),VisDM.class);
  if(!response||response.serviceData.sizeOfPartialErrors()>0||!response.vviStrBuffersOutputMap||response.vviStrBuffersOutputMap.isEmpty())fail('teamcenter_visualization_launch_info_failed');
  var vvi=String(response.vviStrBuffersOutputMap.values().iterator().next()).replace('OperationStructure=Ask','OperationStructure=None');
  vviFile=Files.createTempFile('ai00-tc-vis-','.vvi');Files.write(vviFile,new java.lang.String(vvi).getBytes(StandardCharsets.UTF_8));vvi='';
  var runner=new java.lang.ProcessBuilder('D:\\Siemens\\Teamcenter14\\portal\\runner.exe','-mime=application/x-visnetwork','-encodedArgs='+hex(new java.lang.String(String(vviFile.toAbsolutePath())).getBytes(StandardCharsets.UTF_16BE))).redirectOutput(java.lang.ProcessBuilder.Redirect.DISCARD).redirectError(java.lang.ProcessBuilder.Redirect.DISCARD).start();
  runner.waitFor(90,TimeUnit.SECONDS);
  var launchId='tclaunch:'+String(UUID.randomUUID()).replace(/-/g,'')+String(UUID.randomUUID()).replace(/-/g,'');
  print(JSON.stringify({ok:true,result:{launch_id:launchId,runner_started:true,expected_visdoc_uid:String(payload.expected_visdoc_uid||''),source_identity_hash:String(payload.source_identity_hash||'')}}));exitCode=0;
}catch(error){var message=String(error&&error.message?error.message:error),marker=message.indexOf('AI00_CODE:');var code=marker>=0?message.substring(marker+10).replace(/\s.*$/,''):'teamcenter_visualization_launch_failed';print(JSON.stringify({ok:false,code:code}));}
finally{try{if(session)session.logout();}catch(ignore){}state.user='';state.password='';try{if(vviFile)Files.deleteIfExists(vviFile);}catch(ignoreDelete){}if(connection)connection.release();}
java.lang.System.exit(exitCode);
